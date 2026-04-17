"""
Phase 5 Step 7 — Generate primary signal dataset for v3.0 Meta-Labeler.

For each H1 bar in 2022-04-17 → 2026-04-01 across 5 pairs, walk forward and
ask the production MACD + RSI strategies "would you signal here?". Capture
every YES, then triple-barrier label each one (LdP §3.2):

  - If TP hit first within 48 H1 bars → label = +1 (winner)
  - If SL hit first → label = -1 (loser)
  - If neither hit → label = 0 (timeout)

Outputs:
  data/research/primary_signals.parquet     — full dataset (signals × features × label)
  docs/research/primary_signals_report.md   — stats & analysis
  docs/research/primary_signals_importance.md — re-run feature importance on signals only

Read-only on the DB. No production code modified.
"""
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import warnings
warnings.filterwarnings("ignore")

import sqlite3
import time
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path

from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import cross_val_score, TimeSeriesSplit

from features.ml.feature_engine import build_features, get_feature_columns
from strategies.macd_crossover import MACDCrossoverStrategy
from strategies.rsi_reversal import RSIReversalStrategy

# ───────────────────────────── CONFIG ─────────────────────────────
PAIRS = ["EURUSD", "GBPUSD", "AUDUSD", "USDCAD", "USDCHF"]
START_DATE = "2022-04-17"        # ~4 years (matches v3.0 plan §5.2)
END_DATE = "2026-04-01"
WARMUP_BARS = 250                # need EMA200 + buffer
WINDOW_BARS = 300                # rolling window passed to strategy
TRIPLE_BARRIER_HORIZON = 48      # 48 H1 bars = 2 trading days
MIN_TARGET_SIGNALS = 3000        # plan minimum

DB = "data/trading.db"
OUT_PARQUET = Path("data/research/primary_signals.parquet")
OUT_REPORT = Path("docs/research/primary_signals_report.md")
OUT_IMPORTANCE = Path("docs/research/primary_signals_importance.md")

OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
OUT_REPORT.parent.mkdir(parents=True, exist_ok=True)


# ───────────────────────────── DATA LOAD ─────────────────────────────
def load_h1(symbol: str) -> pd.DataFrame:
    conn = sqlite3.connect(DB)
    df = pd.read_sql(
        """SELECT time, open, high, low, close, volume, spread
           FROM ohlcv_bars
           WHERE symbol = ? AND timeframe = 'H1'
             AND time >= ? AND time < ?
           ORDER BY time""",
        conn,
        params=(symbol, START_DATE, END_DATE),
    )
    conn.close()
    df["time"] = pd.to_datetime(df["time"])
    return df.reset_index(drop=True)


# ───────────────────────────── SIGNAL WALK-FORWARD ─────────────────────────────
def walk_strategies(symbol: str, ohlcv: pd.DataFrame) -> list[dict]:
    """Walk H1 bars and capture every signal each strategy would emit."""
    macd = MACDCrossoverStrategy(symbol=symbol)
    rsi = RSIReversalStrategy(symbol=symbol)

    signals = []
    n = len(ohlcv)
    last_log = time.time()

    for i in range(WARMUP_BARS, n):
        # Rolling window — keeps each call O(WINDOW_BARS) not O(i)
        window = ohlcv.iloc[max(0, i - WINDOW_BARS):i + 1]

        for strat in (macd, rsi):
            sig = strat.generate_signal(window)
            if sig is None:
                continue
            signals.append({
                "time": ohlcv.iloc[i]["time"],
                "symbol": symbol,
                "strategy": sig["strategy"],
                "direction": sig["action"],
                "entry": sig["price"],
                "sl": sig["stop_loss"],
                "tp": sig["take_profit"],
                "atr": sig["atr"],
                "bar_idx": i,
            })

        if time.time() - last_log > 10:
            pct = 100.0 * (i - WARMUP_BARS) / (n - WARMUP_BARS)
            print(f"    {symbol}: {i}/{n} bars  ({pct:.1f}%)  "
                  f"signals so far: {len(signals)}")
            last_log = time.time()

    return signals


# ───────────────────────────── TRIPLE BARRIER ─────────────────────────────
def label_signal(sig: dict, ohlcv: pd.DataFrame) -> dict:
    """Look forward HORIZON bars; return outcome (+1 TP, -1 SL, 0 timeout) + bars-to-resolve."""
    i = sig["bar_idx"]
    end = min(i + TRIPLE_BARRIER_HORIZON + 1, len(ohlcv))
    direction = sig["direction"]
    sl = sig["sl"]
    tp = sig["tp"]

    bars_to_tp = None
    bars_to_sl = None

    for j in range(i + 1, end):
        h = ohlcv.iloc[j]["high"]
        l = ohlcv.iloc[j]["low"]
        if direction == "BUY":
            if bars_to_tp is None and h >= tp:
                bars_to_tp = j - i
            if bars_to_sl is None and l <= sl:
                bars_to_sl = j - i
        else:  # SELL
            if bars_to_tp is None and l <= tp:
                bars_to_tp = j - i
            if bars_to_sl is None and h >= sl:
                bars_to_sl = j - i
        if bars_to_tp is not None and bars_to_sl is not None:
            break

    if bars_to_tp is not None and bars_to_sl is not None:
        if bars_to_tp < bars_to_sl:
            label = 1; bars_held = bars_to_tp; outcome = "TP"
        elif bars_to_sl < bars_to_tp:
            label = -1; bars_held = bars_to_sl; outcome = "SL"
        else:
            label = -1; bars_held = bars_to_tp; outcome = "TIE_to_SL"
    elif bars_to_tp is not None:
        label = 1; bars_held = bars_to_tp; outcome = "TP"
    elif bars_to_sl is not None:
        label = -1; bars_held = bars_to_sl; outcome = "SL"
    else:
        label = 0; bars_held = TRIPLE_BARRIER_HORIZON; outcome = "TIMEOUT"

    # Realized PnL in price terms (for expectancy stats)
    if direction == "BUY":
        pnl_price = (tp - sig["entry"]) if label == 1 else (
            (sl - sig["entry"]) if label == -1 else
            (ohlcv.iloc[min(end - 1, len(ohlcv) - 1)]["close"] - sig["entry"])
        )
    else:
        pnl_price = (sig["entry"] - tp) if label == 1 else (
            (sig["entry"] - sl) if label == -1 else
            (sig["entry"] - ohlcv.iloc[min(end - 1, len(ohlcv) - 1)]["close"])
        )

    return {
        "label": label,
        "outcome": outcome,
        "bars_held": bars_held,
        "pnl_price": pnl_price,
        "rr_ratio": pnl_price / (sig["atr"] if sig["atr"] > 0 else np.nan),
    }


# ───────────────────────────── ATTACH FEATURES ─────────────────────────────
def attach_features(signals: pd.DataFrame, features_df: pd.DataFrame) -> pd.DataFrame:
    """Merge feature snapshot at signal time."""
    feat_subset = features_df[features_df["time"].isin(signals["time"])].copy()
    feat_cols = [c for c in get_feature_columns(features_df)
                 if c in feat_subset.columns and np.issubdtype(feat_subset[c].dtype, np.number)]
    feat_subset = feat_subset[["time"] + feat_cols]
    merged = signals.merge(feat_subset, on="time", how="left")
    return merged, feat_cols


# ───────────────────────────── IMPORTANCE ─────────────────────────────
def importance_on_signals(df: pd.DataFrame, feat_cols: list, target_col: str = "meta_label") -> pd.DataFrame:
    X = df[feat_cols].fillna(0).replace([np.inf, -np.inf], 0)
    y = df[target_col]

    # MDI
    rf = RandomForestClassifier(
        n_estimators=300, max_depth=6, min_samples_leaf=20,
        n_jobs=-1, random_state=42, class_weight="balanced",
    )
    rf.fit(X, y)
    mdi = pd.Series(rf.feature_importances_, index=feat_cols)

    # SFI (smaller, single-feature CV AUC)
    cv = TimeSeriesSplit(n_splits=3)
    sfi = {}
    for f in feat_cols:
        try:
            rf2 = RandomForestClassifier(
                n_estimators=80, max_depth=4, min_samples_leaf=20,
                n_jobs=-1, random_state=42, class_weight="balanced",
            )
            s = cross_val_score(rf2, X[[f]], y, cv=cv, scoring="roc_auc", n_jobs=-1)
            sfi[f] = float(np.mean(s))
        except Exception:
            sfi[f] = np.nan
    sfi = pd.Series(sfi)

    out = pd.DataFrame({"mdi": mdi, "sfi_auc": sfi})
    out["mdi_rank"] = out["mdi"].rank(ascending=False)
    out["sfi_rank"] = (out["sfi_auc"] - 0.5).abs().rank(ascending=False)
    out["consensus"] = (out["mdi_rank"] + out["sfi_rank"]) / 2
    return out.sort_values("consensus")


# ───────────────────────────── MAIN ─────────────────────────────
def main():
    t_start = time.time()
    print(f"\n{'='*72}")
    print(f"  Phase 5 Step 7 — Primary Signal Generation + Triple-Barrier Labels")
    print(f"  Run: {datetime.now().isoformat(timespec='seconds')}")
    print(f"  Window: {START_DATE} → {END_DATE}   pairs: {len(PAIRS)}")
    print(f"  Target: ≥ {MIN_TARGET_SIGNALS:,} signals (plan minimum)")
    print(f"{'='*72}\n")

    all_signals = []
    all_features = []

    for sym in PAIRS:
        print(f"▶ {sym}")
        ohlcv = load_h1(sym)
        if ohlcv.empty:
            print(f"  EMPTY — skip"); continue

        # Pre-compute features once for the whole series (fast, vectorized)
        feat = build_features(ohlcv, dropna=False)

        # Walk forward and capture signals
        sigs = walk_strategies(sym, ohlcv)
        if not sigs:
            print(f"  no signals"); continue
        sigs_df = pd.DataFrame(sigs)
        print(f"  {sym}: bars={len(ohlcv):,}  signals={len(sigs_df):,}  "
              f"(MACD={int((sigs_df['strategy']=='macd_crossover').sum())}, "
              f"RSI={int((sigs_df['strategy']=='rsi_reversal').sum())})")

        # Triple-barrier label each signal
        labels = []
        for _, sig in sigs_df.iterrows():
            res = label_signal(sig.to_dict(), ohlcv)
            labels.append(res)
        labels_df = pd.DataFrame(labels)
        sigs_df = pd.concat([sigs_df.reset_index(drop=True), labels_df], axis=1)

        # Attach feature snapshot at signal time
        merged, feat_cols = attach_features(sigs_df, feat)
        all_signals.append(merged)
        if not all_features:
            all_features.extend(feat_cols)

    if not all_signals:
        print("ERROR: no signals generated"); return

    full = pd.concat(all_signals, ignore_index=True)
    full["meta_label"] = (full["label"] == 1).astype(int)  # binary: profitable or not

    # Stats
    n = len(full)
    by_strat = full.groupby("strategy")["label"].value_counts().unstack(fill_value=0)
    by_pair = full.groupby("symbol")["label"].value_counts().unstack(fill_value=0)

    print(f"\n{'='*72}")
    print(f"  TOTAL signals: {n:,}   "
          f"target: {'✅ MET' if n >= MIN_TARGET_SIGNALS else '❌ BELOW'}")
    print(f"{'='*72}\n")

    print("By strategy:")
    print(by_strat.to_string())
    print("\nBy pair:")
    print(by_pair.to_string())

    win = (full["label"] == 1).sum()
    loss = (full["label"] == -1).sum()
    timeout = (full["label"] == 0).sum()
    wr = 100 * win / max(1, win + loss)
    print(f"\nOverall:  TP={win:,} ({100*win/n:.1f}%)  "
          f"SL={loss:,} ({100*loss/n:.1f}%)  "
          f"TIMEOUT={timeout:,} ({100*timeout/n:.1f}%)")
    print(f"WR (excl timeout): {wr:.1f}%   "
          f"Mean bars held: {full['bars_held'].mean():.1f}")

    # Per-strategy WR
    print("\nWin rate by strategy (excl timeout):")
    for strat, grp in full.groupby("strategy"):
        w = (grp["label"] == 1).sum()
        l = (grp["label"] == -1).sum()
        wr_s = 100 * w / max(1, w + l)
        print(f"  {strat:<18} signals={len(grp):,}  WR={wr_s:.1f}%  "
              f"avg bars held={grp['bars_held'].mean():.1f}")

    # Save dataset
    full.to_parquet(OUT_PARQUET, index=False)
    print(f"\n✓ saved {OUT_PARQUET}  ({len(full):,} rows × {full.shape[1]} cols)")

    # ─── Re-run feature importance ON SIGNALS ONLY ───
    print(f"\n▶ Re-running feature importance on signal subset (binary trade/skip)...")
    valid = full[full["label"] != 0].copy()  # drop timeouts for binary task
    print(f"  Training set: {len(valid):,} signals (excluding {timeout:,} timeouts)")

    imp = importance_on_signals(valid, all_features, target_col="meta_label")
    top20 = imp.head(20)

    print(f"\n  Top 20 features for Meta-Labeler (consensus rank):")
    for i, (f, row) in enumerate(top20.iterrows(), 1):
        print(f"    {i:>2}. {f:<32}  MDI={row['mdi']:.4f}  SFI AUC={row['sfi_auc']:.4f}")

    # ─── Write reports ───
    md = []
    md.append(f"# Phase 5 Step 7 — Primary Signal Dataset (v3.0 Meta-Labeler training set)\n")
    md.append(f"_Generated: {datetime.now().isoformat(timespec='seconds')}_  ")
    md.append(f"_Window: {START_DATE} → {END_DATE} · {len(PAIRS)} pairs · H1_  ")
    md.append(f"_Strategies: macd_crossover v2.0, rsi_reversal v1.1 (production code)_  ")
    md.append(f"_Triple barrier: TP/SL from each strategy's own ATR multipliers, horizon={TRIPLE_BARRIER_HORIZON} H1 bars (2 trading days)_\n")

    status = "✅ MET" if n >= MIN_TARGET_SIGNALS else "❌ BELOW"
    md.append(f"## Result: {n:,} signals (target {MIN_TARGET_SIGNALS:,} → {status})\n")

    md.append("## Signal counts by strategy\n")
    md.append("| Strategy | Total | TP (+1) | SL (-1) | Timeout (0) | WR (excl timeout) |")
    md.append("|---|---:|---:|---:|---:|---:|")
    for strat, grp in full.groupby("strategy"):
        w = (grp["label"] == 1).sum()
        l = (grp["label"] == -1).sum()
        t = (grp["label"] == 0).sum()
        wr_s = 100 * w / max(1, w + l)
        md.append(f"| `{strat}` | {len(grp):,} | {w:,} | {l:,} | {t:,} | {wr_s:.1f}% |")

    md.append("\n## Signal counts by pair\n")
    md.append("| Pair | Total | TP | SL | Timeout | WR |")
    md.append("|---|---:|---:|---:|---:|---:|")
    for sym, grp in full.groupby("symbol"):
        w = (grp["label"] == 1).sum()
        l = (grp["label"] == -1).sum()
        t = (grp["label"] == 0).sum()
        wr_s = 100 * w / max(1, w + l)
        md.append(f"| `{sym}` | {len(grp):,} | {w:,} | {l:,} | {t:,} | {wr_s:.1f}% |")

    md.append("\n## Reading the win rate\n")
    md.append("- A primary signal's WR is **before** the meta-labeler filter. The meta-labeler's job is to push this WR up by rejecting low-quality signals.")
    md.append(f"- Overall WR is **{wr:.1f}%**. With TP/SL ratios > 1, even WR ~45% can be profitable — but the v3.0 target is to lift WR closer to 55-60% via meta-filtering.")
    md.append(f"- **{timeout:,} timeouts** ({100*timeout/n:.1f}%) are signals where neither TP nor SL hit within {TRIPLE_BARRIER_HORIZON} H1 bars. These are kept in the dataset (label=0) but excluded from the binary trade/skip training set.")

    md.append("\n## Dataset contents\n")
    md.append(f"`{OUT_PARQUET}` — {len(full):,} rows × {full.shape[1]} columns:")
    md.append("- Identification: `time, symbol, strategy, direction, bar_idx`")
    md.append("- Trade params: `entry, sl, tp, atr`")
    md.append("- Outcome: `label, outcome, bars_held, pnl_price, rr_ratio`")
    md.append("- Meta-label: `meta_label` (1 = profitable, 0 = not)")
    md.append(f"- Features: {len(all_features)} columns (snapshot at signal time)")

    md.append("\n## Next step\n")
    md.append("This dataset is the input for `ml/meta_labeler.py` (v3.0 Phase 7). "
              "It also feeds the re-run feature importance below — those rankings, not "
              "the every-bar ones from step 6, are what should drive the final feature set.\n")

    OUT_REPORT.write_text("\n".join(md), encoding="utf-8")
    print(f"\n✓ saved {OUT_REPORT}")

    md2 = []
    md2.append(f"# Phase 5 Step 7 — Feature Importance on Primary Signals\n")
    md2.append(f"_Re-ran MDI + SFI on signal-conditioned subset ({len(valid):,} rows, binary meta-label)_\n")
    md2.append("This ranking matters more than step 6's every-bar ranking — these are the features that distinguish good from bad MACD/RSI signals, not random H1 bars.\n")
    md2.append("## Top 20 features for v3.0 Meta-Labeler\n")
    md2.append("| # | Feature | MDI | SFI (AUC) | Consensus rank |")
    md2.append("|---|---|---:|---:|---:|")
    for i, (f, row) in enumerate(top20.iterrows(), 1):
        md2.append(f"| {i} | `{f}` | {row['mdi']:.4f} | {row['sfi_auc']:.4f} | {row['consensus']:.1f} |")

    md2.append(f"\n## Comparison to step 6 (every-bar)\n")
    md2.append("Step 6 found all SFI AUCs in [0.49, 0.51] — random. If step-7 SFI AUCs are higher (e.g., several > 0.55), the meta-labeling architecture has measurable signal to work with.\n")
    above_55 = (imp["sfi_auc"] > 0.55).sum()
    above_53 = (imp["sfi_auc"] > 0.53).sum()
    md2.append(f"- Features with SFI AUC > 0.55: **{above_55}**")
    md2.append(f"- Features with SFI AUC > 0.53: **{above_53}**")
    md2.append(f"- Best SFI AUC: **{imp['sfi_auc'].max():.4f}** (`{imp['sfi_auc'].idxmax()}`)\n")

    if above_55 >= 5:
        verdict = "✅ **Strong meta-labeler signal**. The pivot to filtering primary signals is validated by data — multiple features have measurable predictive power on signal quality."
    elif above_53 >= 5:
        verdict = "⚠️ **Weak but present meta-labeler signal**. Marginal — proceed but expect Sharpe gains < 30% rather than the 30-50% Hudson & Thames cite."
    else:
        verdict = "❌ **No measurable signal even at signal-conditioned level**. Reconsider: maybe MACD/RSI primary signals are noise too. Investigate before building meta-labeler."
    md2.append(f"## Verdict\n\n{verdict}\n")

    OUT_IMPORTANCE.write_text("\n".join(md2), encoding="utf-8")
    print(f"✓ saved {OUT_IMPORTANCE}")

    elapsed = time.time() - t_start
    print(f"\n{'='*72}")
    print(f"  ✅ DONE in {elapsed:.0f}s — {n:,} signals, "
          f"{(full['label']==1).sum():,} winners, "
          f"{(imp['sfi_auc'] > 0.55).sum()} features with AUC > 0.55")
    print(f"{'='*72}\n")


if __name__ == "__main__":
    main()
