"""
Phase 5 extra — Expectancy analysis per (strategy, pair)

WR alone doesn't tell you if a strategy makes money. Expectancy does:
    expectancy = (WR × avg_win) - ((1-WR) × avg_loss)

A strategy with WR=35% but 3:1 RR is profitable. A strategy with WR=60%
but 1:2 RR is not. ml_direct @ XAUUSD had WR=75.7% and still lost $17K.

Compute expectancy from TWO sources:
  1. Backtest: 1,144 primary signals with triple-barrier outcomes
     (exact PnL in ATR units since TP/SL are known)
  2. Live: 211 closed trades from trades table ($ PnL per trade)

Compare:
  - Raw primary (no meta-filter)
  - Meta-filtered (only signals the RSI meta-labeler would take)

Writes results to:
  - data/improvements.db → expectancy_analysis table (new)
  - docs/research/expectancy_report.md
"""
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import warnings
warnings.filterwarnings("ignore")

import sqlite3
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path

from lightgbm import LGBMClassifier
from sklearn.model_selection import KFold

SIGNALS_PARQUET = Path("data/research/primary_signals.parquet")
TRADING_DB = "data/trading.db"
IMP_DB = "data/improvements.db"
OUT_REPORT = Path("docs/research/expectancy_report.md")

DECISION_THRESHOLD = 0.55
N_SPLITS = 5

TOP_FEATURES = [
    "candle_body_ratio", "price_position_50", "lower_shadow_ratio",
    "close_vs_sma_200", "macd_hist", "volatility_10",
    "price_vs_high_20_atr", "rsi_14_lag1", "rsi_14_lag2", "macd_hist_lag1",
    "volume_ratio", "atr_28_pct", "price_position_10", "volume_change",
    "body_vs_atr", "atr_ratio_20", "macd_hist_change", "ema_12",
    "return_5", "dist_from_high_20",
]


def expectancy_from_backtest(df, label_col="label") -> dict:
    """Signals use triple-barrier: win = +tp_mult×ATR, loss = -sl_mult×ATR.
    We have exact rr_ratio per signal (pnl_price / atr) so compute directly."""
    if df.empty:
        return None
    wins = df[df[label_col] == 1]
    losses = df[df[label_col] == -1]
    timeouts = df[df[label_col] == 0]

    n_decisive = len(wins) + len(losses)
    n_all = len(df)
    if n_decisive == 0:
        return None

    wr = len(wins) / n_decisive
    avg_win_atr = wins["rr_ratio"].mean() if len(wins) else 0.0
    avg_loss_atr = abs(losses["rr_ratio"].mean()) if len(losses) else 0.0

    # Expectancy per signal, in ATR units (including timeouts as 0 approx)
    exp_atr_per_decisive = wr * avg_win_atr - (1 - wr) * avg_loss_atr
    exp_atr_per_signal = exp_atr_per_decisive * (n_decisive / n_all)

    # Convert ATR to pips (rough: assume 1 ATR ≈ 20 pips for majors, 100 pips for XAU)
    # More accurately: use the raw `atr` column which is in price units
    avg_atr_price = df["atr"].mean()
    # For majors, pip value ~ 0.0001; for JPY pairs ~ 0.01; for XAU ~ 0.1
    # Infer from entry price magnitude:
    avg_entry = df["entry"].mean()
    if avg_entry > 500:          # XAU
        pip_scale = 0.1
    elif avg_entry > 50:         # JPY
        pip_scale = 0.01
    else:                        # majors
        pip_scale = 0.0001
    avg_atr_pips = avg_atr_price / pip_scale
    exp_pips_per_signal = exp_atr_per_signal * avg_atr_pips

    return {
        "n_signals": n_all,
        "n_decisive": n_decisive,
        "n_timeouts": len(timeouts),
        "wr": wr * 100,
        "avg_win_atr": avg_win_atr,
        "avg_loss_atr": avg_loss_atr,
        "avg_atr_pips": avg_atr_pips,
        "rr_ratio": avg_win_atr / avg_loss_atr if avg_loss_atr > 0 else None,
        "expectancy_atr": exp_atr_per_signal,
        "expectancy_pips": exp_pips_per_signal,
    }


def expectancy_from_live_trades(conn) -> pd.DataFrame:
    """Live trade expectancy per (strategy, symbol) from trades table."""
    df = pd.read_sql("""
        SELECT strategy, symbol, profit
        FROM trades WHERE is_closed = 1
    """, conn)
    rows = []
    for (strat, sym), grp in df.groupby(["strategy", "symbol"]):
        n = len(grp)
        wins = grp[grp.profit > 0]
        losses = grp[grp.profit <= 0]
        wr = len(wins) / n if n else 0
        avg_win = wins.profit.mean() if len(wins) else 0
        avg_loss = abs(losses.profit.mean()) if len(losses) else 0
        exp = wr * avg_win - (1 - wr) * avg_loss
        rows.append({
            "strategy": strat, "symbol": sym, "n": n,
            "wr": wr * 100, "avg_win_usd": avg_win, "avg_loss_usd": avg_loss,
            "rr_ratio": avg_win / avg_loss if avg_loss > 0 else None,
            "expectancy_usd": exp,
            "total_pnl": grp.profit.sum(),
        })
    return pd.DataFrame(rows)


def train_rsi_meta_labeler(df_all):
    """Train meta-labeler on RSI signals and return per-signal probabilities.
    Uses out-of-fold predictions so every signal gets a prediction made
    without that signal in the training set."""
    rsi = df_all[df_all["strategy"] == "rsi_reversal"].copy()
    rsi = rsi[rsi["label"] != 0].sort_values("time").reset_index(drop=True)
    if len(rsi) < 50:
        return None

    feats = [c for c in TOP_FEATURES if c in rsi.columns]
    X = rsi[feats].fillna(0).replace([np.inf, -np.inf], 0).values
    y = (rsi["label"] == 1).astype(int).values

    kf = KFold(n_splits=N_SPLITS, shuffle=False)
    preds = np.full(len(rsi), np.nan)

    for train_idx, test_idx in kf.split(X):
        if len(np.unique(y[train_idx])) < 2:
            continue
        m = LGBMClassifier(
            n_estimators=200, learning_rate=0.05, max_depth=5,
            num_leaves=16, min_child_samples=20,
            class_weight="balanced", n_jobs=-1, random_state=42, verbose=-1,
        )
        m.fit(X[train_idx], y[train_idx])
        preds[test_idx] = m.predict_proba(X[test_idx])[:, 1]

    rsi["meta_proba"] = preds
    rsi["meta_take"] = (preds >= DECISION_THRESHOLD).astype(int)
    return rsi


def ensure_schema():
    conn = sqlite3.connect(IMP_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS expectancy_analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_time TEXT NOT NULL,
            source TEXT NOT NULL,           -- backtest, live, meta_filtered
            strategy TEXT NOT NULL,
            symbol TEXT,
            scope_label TEXT,
            n_signals INTEGER,
            wr_pct REAL,
            avg_win REAL,
            avg_loss REAL,
            rr_ratio REAL,
            expectancy_per_signal REAL,
            unit TEXT,                      -- 'pips', 'usd', 'atr'
            extras TEXT
        )
    """)
    conn.commit()
    conn.close()


def main():
    print(f"\n{'='*72}")
    print(f"  Expectancy Analysis — Phase 5 research")
    print(f"  Run: {datetime.now().isoformat(timespec='seconds')}")
    print(f"{'='*72}\n")

    ensure_schema()
    run_time = datetime.now().isoformat(timespec="seconds")
    rows_to_save = []

    # ─── 1. Backtest expectancy per combo ───
    print(f"▶ Loading backtest signals: {SIGNALS_PARQUET}")
    sig = pd.read_parquet(SIGNALS_PARQUET)
    print(f"  {len(sig):,} signals loaded")

    print(f"\n▶ Backtest expectancy per (strategy, pair):")
    print(f"  {'Strategy':<18} {'Pair':<7} {'N':>4} {'WR':>6} {'Win×ATR':>8} {'Loss×ATR':>9} {'RR':>5} {'Exp/sig(ATR)':>13} {'Exp(pips)':>10}")
    print(f"  {'-'*18} {'-'*7} {'-'*4} {'-'*6} {'-'*8} {'-'*9} {'-'*5} {'-'*13} {'-'*10}")
    for (strat, sym), grp in sig.groupby(["strategy", "symbol"]):
        res = expectancy_from_backtest(grp)
        if not res:
            continue
        print(
            f"  {strat:<18} {sym:<7} "
            f"{res['n_signals']:>4} {res['wr']:>5.1f}% "
            f"{res['avg_win_atr']:>8.2f} {res['avg_loss_atr']:>9.2f} "
            f"{(res['rr_ratio'] or 0):>5.2f} "
            f"{res['expectancy_atr']:>13.3f} {res['expectancy_pips']:>10.1f}"
        )
        rows_to_save.append((
            run_time, "backtest", strat, sym, f"{strat}/{sym}",
            res['n_signals'], res['wr'],
            res['avg_win_atr'], -res['avg_loss_atr'],
            res['rr_ratio'], res['expectancy_pips'], "pips",
            f"atr={res['avg_atr_pips']:.1f}, decisive={res['n_decisive']}, timeouts={res['n_timeouts']}"
        ))

    # Per-strategy summary
    print(f"\n▶ Backtest expectancy per strategy (pooled):")
    for strat, grp in sig.groupby("strategy"):
        res = expectancy_from_backtest(grp)
        if not res:
            continue
        print(
            f"  {strat:<18} n={res['n_signals']:>4} WR={res['wr']:5.1f}%  "
            f"RR={(res['rr_ratio'] or 0):.2f}  Exp={res['expectancy_pips']:+.1f} pips/signal"
        )
        rows_to_save.append((
            run_time, "backtest", strat, None, f"{strat}_pooled",
            res['n_signals'], res['wr'],
            res['avg_win_atr'], -res['avg_loss_atr'],
            res['rr_ratio'], res['expectancy_pips'], "pips",
            f"atr={res['avg_atr_pips']:.1f}"
        ))

    # ─── 2. Live trade expectancy ───
    print(f"\n▶ Live trade expectancy per (strategy, pair):")
    conn_t = sqlite3.connect(TRADING_DB)
    live = expectancy_from_live_trades(conn_t)
    conn_t.close()
    if not live.empty:
        live = live.sort_values("expectancy_usd", ascending=False)
        print(f"  {'Strategy':<20} {'Pair':<8} {'N':>4} {'WR':>6} {'AvgWin$':>9} {'AvgLoss$':>10} {'RR':>5} {'Exp/trade':>10} {'Total$':>10}")
        print(f"  {'-'*20} {'-'*8} {'-'*4} {'-'*6} {'-'*9} {'-'*10} {'-'*5} {'-'*10} {'-'*10}")
        for _, r in live.iterrows():
            print(
                f"  {r['strategy']:<20} {r['symbol']:<8} "
                f"{int(r['n']):>4} {r['wr']:>5.1f}% "
                f"${r['avg_win_usd']:>7.0f} ${r['avg_loss_usd']:>8.0f} "
                f"{(r['rr_ratio'] or 0):>5.2f} "
                f"${r['expectancy_usd']:>+9.0f} ${r['total_pnl']:>+9.0f}"
            )
            rows_to_save.append((
                run_time, "live", r['strategy'], r['symbol'],
                f"{r['strategy']}/{r['symbol']}",
                int(r['n']), r['wr'],
                r['avg_win_usd'], -r['avg_loss_usd'],
                r['rr_ratio'], r['expectancy_usd'], "usd",
                f"total_pnl={r['total_pnl']:.2f}"
            ))

    # ─── 3. Meta-filtered RSI expectancy ───
    print(f"\n▶ Meta-filtered RSI expectancy (out-of-fold LGBM predictions):")
    rsi_meta = train_rsi_meta_labeler(sig)
    if rsi_meta is None:
        print("  SKIP — not enough RSI data")
    else:
        # Raw
        raw_res = expectancy_from_backtest(rsi_meta)
        # Filtered
        filt = rsi_meta[rsi_meta["meta_take"] == 1]
        filt_res = expectancy_from_backtest(filt) if len(filt) else None
        print(f"  Raw RSI   : n={raw_res['n_signals']:>4}  WR={raw_res['wr']:5.1f}%  Exp={raw_res['expectancy_pips']:+.1f} pips")
        if filt_res:
            keep_rate = 100 * filt_res['n_signals'] / raw_res['n_signals']
            lift_pips = filt_res['expectancy_pips'] - raw_res['expectancy_pips']
            print(f"  Filtered  : n={filt_res['n_signals']:>4}  WR={filt_res['wr']:5.1f}%  Exp={filt_res['expectancy_pips']:+.1f} pips  (keep {keep_rate:.0f}%, lift {lift_pips:+.1f} pips)")
            rows_to_save.append((
                run_time, "meta_filtered", "rsi_reversal", None,
                "rsi_filtered_proba>=0.55",
                filt_res['n_signals'], filt_res['wr'],
                filt_res['avg_win_atr'], -filt_res['avg_loss_atr'],
                filt_res['rr_ratio'], filt_res['expectancy_pips'], "pips",
                f"keep_rate={keep_rate:.1f}%, raw_exp={raw_res['expectancy_pips']:.1f}"
            ))

        # Per RSI keepable pair (EURUSD, AUDUSD, GBPUSD from step 8 decision)
        print(f"\n  Per-pair RSI with meta filter:")
        for sym in ["EURUSD", "AUDUSD", "GBPUSD"]:
            sub_raw = rsi_meta[rsi_meta["symbol"] == sym]
            sub_filt = sub_raw[sub_raw["meta_take"] == 1]
            if len(sub_raw) < 5:
                continue
            r_raw = expectancy_from_backtest(sub_raw)
            r_filt = expectancy_from_backtest(sub_filt) if len(sub_filt) >= 3 else None
            if r_raw and r_filt:
                print(f"    {sym}: raw n={r_raw['n_signals']} WR={r_raw['wr']:.0f}% Exp={r_raw['expectancy_pips']:+.1f}  |  filt n={r_filt['n_signals']} WR={r_filt['wr']:.0f}% Exp={r_filt['expectancy_pips']:+.1f} pips")
            elif r_raw:
                print(f"    {sym}: raw n={r_raw['n_signals']} WR={r_raw['wr']:.0f}% Exp={r_raw['expectancy_pips']:+.1f}  |  filt: too few taken")

    # ─── Save all rows ───
    conn = sqlite3.connect(IMP_DB)
    for row in rows_to_save:
        conn.execute("""
            INSERT INTO expectancy_analysis
            (run_time, source, strategy, symbol, scope_label, n_signals, wr_pct,
             avg_win, avg_loss, rr_ratio, expectancy_per_signal, unit, extras)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, row)
    conn.commit()
    conn.close()
    print(f"\n✓ saved {len(rows_to_save)} rows to expectancy_analysis table")

    # ─── Markdown report ───
    md = []
    md.append(f"# Expectancy Analysis — v3.0 Phase 5\n")
    md.append(f"_Run: {run_time}_\n")
    md.append(f"Expectancy = (WR × avg_win) − ((1−WR) × avg_loss). ")
    md.append(f"Positive = strategy makes money on average. Negative = loses money.\n")

    md.append("## Backtest expectancy (triple-barrier signals)\n")
    md.append("| Strategy | Pair | N | WR | RR | Exp (pips/signal) |")
    md.append("|---|---|---:|---:|---:|---:|")
    for (strat, sym), grp in sig.groupby(["strategy", "symbol"]):
        r = expectancy_from_backtest(grp)
        if not r: continue
        md.append(f"| `{strat}` | `{sym}` | {r['n_signals']} | {r['wr']:.1f}% | {(r['rr_ratio'] or 0):.2f} | {r['expectancy_pips']:+.1f} |")

    md.append("\n## Live trade expectancy (211 closed trades)\n")
    md.append("| Strategy | Pair | N | WR | AvgWin$ | AvgLoss$ | Exp/trade | Total PnL |")
    md.append("|---|---|---:|---:|---:|---:|---:|---:|")
    for _, r in live.iterrows():
        md.append(f"| `{r['strategy']}` | `{r['symbol']}` | {int(r['n'])} | {r['wr']:.1f}% | ${r['avg_win_usd']:.0f} | ${r['avg_loss_usd']:.0f} | ${r['expectancy_usd']:+.0f} | ${r['total_pnl']:+.0f} |")

    if rsi_meta is not None:
        md.append("\n## Meta-filter impact on RSI\n")
        raw_res = expectancy_from_backtest(rsi_meta)
        filt = rsi_meta[rsi_meta["meta_take"] == 1]
        filt_res = expectancy_from_backtest(filt) if len(filt) else None
        md.append(f"- **Raw RSI** (all 307 signals): WR {raw_res['wr']:.1f}%, Exp {raw_res['expectancy_pips']:+.1f} pips/signal")
        if filt_res:
            md.append(f"- **Filtered RSI** (proba ≥ 0.55): WR {filt_res['wr']:.1f}%, Exp {filt_res['expectancy_pips']:+.1f} pips/signal")
            md.append(f"- **Keep-rate**: {100*filt_res['n_signals']/raw_res['n_signals']:.0f}% of signals taken")
            md.append(f"- **Lift**: {filt_res['expectancy_pips']-raw_res['expectancy_pips']:+.1f} pips per signal\n")

    md.append("\n## How to read this\n")
    md.append("- **RR < 1.0** means losses are bigger than wins. Need high WR to survive.")
    md.append("- **Exp/signal negative** → strategy is a money-loser regardless of win rate.")
    md.append("- **Live vs backtest gap** shows execution reality (slippage, spreads, psychology).")
    md.append("- Meta-filtered columns show the expected lift IF the meta-labeler generalizes out of sample — always expect some degradation in production.\n")

    OUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUT_REPORT.write_text("\n".join(md), encoding="utf-8")
    print(f"✓ report: {OUT_REPORT}")

    print(f"\n{'='*72}")
    print(f"  DONE — see {OUT_REPORT}")
    print(f"{'='*72}\n")


if __name__ == "__main__":
    main()
