"""Paper-to-Live fidelity audit data gathering.

READ-ONLY. Uses the MT5Adapter pattern to connect to the engine's actual
account (MetaQuotes-Demo / login from .env), then samples live data alongside
static codebase + DB analysis. Produces dict outputs that the report-writing
phase consumes.

Sections covered:
  1. Account configuration (live)
  2. Lot sizing logic (static + DB)
  3. Slippage and execution fidelity (DB-derived)
  4. Spread and commission (DB + live sampling)
  5. Swap accounting (DB-derived)
  6. News filter (static + DB)
  7. Structural differences (static)
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, ".")

# Force right terminal per .env
import MetaTrader5 as mt5

ROOT = Path(".")
TRADING_DB = "data/trading.db"
OUT_JSON = Path("artifacts/live_fidelity_audit_data.json")

SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "AUDUSD", "USDCAD", "USDCHF"]


def connect():
    path = os.getenv("MT5_PATH", "")
    login = int(os.getenv("MT5_LOGIN", "0"))
    password = os.getenv("MT5_PASSWORD", "")
    server = os.getenv("MT5_SERVER", "")
    if path:
        if not mt5.initialize(path=path):
            return False, f"initialize(path) failed: {mt5.last_error()}"
    elif not mt5.initialize():
        return False, f"initialize() failed: {mt5.last_error()}"
    info = mt5.account_info()
    if info is None or info.login != login:
        ok = mt5.login(login, password=password, server=server)
        if not ok:
            return False, f"login() failed: {mt5.last_error()}"
    info = mt5.account_info()
    return True, info


def section_1():
    print("=" * 78)
    print("SECTION 1 — Account configuration")
    print("=" * 78)
    ok, info = connect()
    out = {"section": 1, "connected": ok}
    if not ok:
        print(f"[FAIL] {info}")
        out["error"] = str(info)
        return out
    d = info._asdict()
    out["account"] = {k: d[k] for k in
        ["login", "server", "trade_mode", "leverage", "currency",
         "balance", "equity", "margin", "margin_free", "margin_level",
         "margin_so_call", "margin_so_so", "trade_allowed", "company"]}
    print(f"  login={d['login']} server={d['server']} trade_mode={d['trade_mode']} leverage=1:{d['leverage']}")
    print(f"  balance={d['balance']:,.2f} {d['currency']}  equity={d['equity']:,.2f}")

    # Per-symbol specs (Section 1.3)
    out["symbols"] = {}
    print()
    print(f"{'symbol':8s} {'pt':>6s} {'tick_sz':>10s} {'tick_v':>10s} {'min_v':>6s} {'max_v':>8s} {'step':>6s} {'init_marg':>10s} {'sw_long':>8s} {'sw_short':>8s} {'rollover':>3s} {'mode':>5s} {'spread':>7s}")
    for sym in SYMBOLS:
        si = mt5.symbol_info(sym)
        if si is None:
            print(f"  {sym:8s} <not found>")
            continue
        si_d = si._asdict()
        out["symbols"][sym] = {
            "point": si_d.get("point"),
            "tick_size": si_d.get("trade_tick_size"),
            "tick_value": si_d.get("trade_tick_value"),
            "contract_size": si_d.get("trade_contract_size"),
            "volume_min": si_d.get("volume_min"),
            "volume_max": si_d.get("volume_max"),
            "volume_step": si_d.get("volume_step"),
            "margin_initial": si_d.get("margin_initial"),
            "margin_maintenance": si_d.get("margin_maintenance"),
            "swap_long": si_d.get("swap_long"),
            "swap_short": si_d.get("swap_short"),
            "swap_rollover3days": si_d.get("swap_rollover3days"),
            "trade_mode": si_d.get("trade_mode"),
            "filling_mode": si_d.get("filling_mode"),
            "spread": si_d.get("spread"),
        }
        print(f"  {sym:8s} {si_d.get('point'):>6.5f} {si_d.get('trade_tick_size'):>10.5f} "
              f"{si_d.get('trade_tick_value'):>10.5f} {si_d.get('volume_min'):>6.2f} "
              f"{si_d.get('volume_max'):>8.0f} {si_d.get('volume_step'):>6.2f} "
              f"{si_d.get('margin_initial'):>10.2f} {si_d.get('swap_long'):>8.4f} "
              f"{si_d.get('swap_short'):>8.4f} {si_d.get('swap_rollover3days'):>3d} "
              f"{si_d.get('trade_mode'):>5d} {si_d.get('spread'):>7d}")

    # Section 7.2 clock drift
    tick = mt5.symbol_info_tick("EURUSD")
    if tick:
        broker_t = datetime.fromtimestamp(tick.time, tz=timezone.utc)
        local_t = datetime.now(timezone.utc)
        drift = abs((broker_t - local_t).total_seconds())
        out["clock_drift_seconds"] = round(drift, 1)
        print(f"\n  clock drift broker vs local UTC: {drift:.1f}s ({'FLAG' if drift > 5 else 'OK'})")

    return out


def section_2(deps):
    print()
    print("=" * 78)
    print("SECTION 2 — Lot sizing logic")
    print("=" * 78)
    out = {"section": 2}

    # 2.1 Find lot calculation
    risk_files = list(Path("risk").glob("*.py")) if Path("risk").exists() else []
    lot_calc_file = None
    lot_calc_excerpt = None
    for f in risk_files:
        src = f.read_text(encoding="utf-8", errors="ignore")
        if "calculate_position_size" in src or "lot_size" in src.lower():
            lot_calc_file = str(f)
            m = re.search(r"def\s+(calculate_position_size|calc_lot|position_size)[^\n]*\n((?:    [^\n]*\n){5,40})", src)
            if m:
                lot_calc_excerpt = m.group(0)[:1500]
            break
    out["lot_calc_file"] = lot_calc_file
    if lot_calc_excerpt:
        print(f"  found: {lot_calc_file}")
        print("  excerpt (truncated):")
        for line in lot_calc_excerpt.split("\n")[:18]:
            print(f"    {line}")

    # 2.2 Reproduce on last 5 closed trades
    print()
    print("--- 2.2 Last 5 closed v3 trades — actual vs theoretical lot ---")
    con = sqlite3.connect(TRADING_DB)
    rows = con.execute(
        "SELECT t.ticket, t.symbol, t.volume, t.open_price, t.stop_loss, "
        "tr.atr_at_entry, t.open_time "
        "FROM trades t LEFT JOIN trade_results tr ON t.ticket=tr.ticket "
        "WHERE t.is_closed=1 AND t.engine_version='2.4' AND t.open_time >= '2026-04-10' "
        "ORDER BY t.open_time DESC LIMIT 5"
    ).fetchall()
    con.close()

    out["last5_lot_repro"] = []
    for r in rows:
        ticket, sym, vol, op, sl, atr, ot = r
        # SL distance in pips (rough — needs symbol pip_value)
        if sym and "JPY" in sym:
            pip = 0.01
        elif sym == "XAUUSD":
            pip = 0.01
        else:
            pip = 0.0001
        if sl and op:
            sl_dist_raw = abs(op - sl)
            sl_pips = sl_dist_raw / pip if pip > 0 else 0
        else:
            sl_pips = 0
        out["last5_lot_repro"].append({
            "ticket": ticket, "symbol": sym, "open_time": str(ot),
            "actual_volume": vol, "open_price": op, "stop_loss": sl,
            "atr_at_entry": atr, "sl_distance_pips_approx": round(sl_pips, 2),
        })
        print(f"  {ticket} {sym:7s} vol={vol:.2f} entry={op:.5f} SL={sl:.5f} sl_pips≈{sl_pips:.1f} ATR={atr}")

    # 2.4 Lot rounding from config
    print()
    print("--- 2.4 Configured lot constraints ---")
    import yaml
    cfg = yaml.safe_load(Path("config/paper.yaml").read_text(encoding="utf-8"))
    risk = cfg.get("risk", {})
    out["risk_config"] = risk
    for k, v in risk.items():
        print(f"  {k}: {v}")

    return out


def section_3():
    print()
    print("=" * 78)
    print("SECTION 3 — Slippage and execution fidelity")
    print("=" * 78)
    out = {"section": 3}

    # 3.1 Slippage column?
    con = sqlite3.connect(TRADING_DB)
    cols_tr = [r[1] for r in con.execute("PRAGMA table_info(trade_results)").fetchall()]
    has_slip = "slippage_pips" in cols_tr
    out["has_slippage_column"] = has_slip
    print(f"  trade_results.slippage_pips column: {'YES' if has_slip else 'NO'}")

    if has_slip:
        slip_stats = con.execute(
            "SELECT symbol, COUNT(slippage_pips), AVG(slippage_pips), MIN(slippage_pips), MAX(slippage_pips), "
            "AVG(ABS(slippage_pips)) "
            "FROM trade_results WHERE engine_version='2.4' AND open_time>='2026-04-10' "
            "AND slippage_pips IS NOT NULL GROUP BY symbol"
        ).fetchall()
        out["slippage_per_symbol"] = []
        if slip_stats:
            print(f"  per symbol  | n  | mean    | min     | max     | mean(abs)")
            for s, n, mn, mi, mx, mab in slip_stats:
                print(f"  {s:11s} | {n:2d} | {(mn or 0):+.4f} | {(mi or 0):+.4f} | {(mx or 0):+.4f} | {(mab or 0):.4f}")
                out["slippage_per_symbol"].append({"symbol": s, "n": n, "mean": mn, "min": mi, "max": mx, "mean_abs": mab})
        else:
            print("  no slippage data captured (all NULL)")
        nonzero = con.execute(
            "SELECT COUNT(*) FROM trade_results WHERE slippage_pips IS NOT NULL AND slippage_pips != 0 "
            "AND engine_version='2.4' AND open_time>='2026-04-10'"
        ).fetchone()[0]
        total = con.execute(
            "SELECT COUNT(*) FROM trade_results WHERE engine_version='2.4' AND open_time>='2026-04-10'"
        ).fetchone()[0]
        print(f"  trades with non-zero slippage: {nonzero} / {total}")
        out["slippage_nonzero_count"] = nonzero
        out["slippage_total_v3"] = total

    # 3.2 OrderSend retcode logging? scan log for retcode patterns
    log_path = Path("data/logs/paper_trading.log")
    retcode_matches = {}
    if log_path.exists():
        log = log_path.read_text(encoding="utf-8", errors="ignore")
        for code, name in [
            (10009, "TRADE_RETCODE_DONE"),
            (10004, "TRADE_RETCODE_REQUOTE"),
            (10013, "TRADE_RETCODE_INVALID"),
            (10018, "TRADE_RETCODE_MARKET_CLOSED"),
            (10006, "TRADE_RETCODE_REJECT"),
            (10027, "TRADE_RETCODE_LIMIT_VOLUME"),
        ]:
            n = log.count(str(code))
            if n > 0:
                retcode_matches[code] = (name, n)
    print(f"\n  retcode mentions in paper_trading.log: {dict((k, v[1]) for k, v in retcode_matches.items())}")
    out["retcode_log_mentions"] = {str(k): {"name": v[0], "count": v[1]} for k, v in retcode_matches.items()}

    # 3.3 SL/TP server-side or client-side?
    adapter = Path("execution/broker_adapters/mt5_adapter.py").read_text(encoding="utf-8")
    has_sl_in_request = bool(re.search(r"\"sl\"\s*:|\.sl\s*=", adapter))
    has_tp_in_request = bool(re.search(r"\"tp\"\s*:|\.tp\s*=", adapter))
    has_modify = "order_modify" in adapter.lower() or "TRADE_ACTION_SLTP" in adapter
    print(f"  SL/TP submitted with order: sl={has_sl_in_request} tp={has_tp_in_request}")
    print(f"  Has separate modify path: {has_modify}")
    out["sltp_server_side"] = has_sl_in_request and has_tp_in_request
    out["has_modify_path"] = has_modify

    con.close()
    return out


def section_4(deps):
    print()
    print("=" * 78)
    print("SECTION 4 — Spread and commission")
    print("=" * 78)
    out = {"section": 4}

    # 4.1 Commission column?
    con = sqlite3.connect(TRADING_DB)
    cols = [r[1] for r in con.execute("PRAGMA table_info(trades)").fetchall()]
    has_comm = "commission" in cols
    print(f"  trades.commission column: {'YES' if has_comm else 'NO'}")
    out["has_commission_column"] = has_comm

    if has_comm:
        comm_stats = con.execute(
            "SELECT symbol, COUNT(*), SUM(commission), AVG(commission), "
            "SUM(CASE WHEN commission != 0 THEN 1 ELSE 0 END) "
            "FROM trades WHERE engine_version='2.4' AND open_time>='2026-04-10' "
            "AND is_closed=1 GROUP BY symbol"
        ).fetchall()
        print(f"  commission per symbol (v3 closed):")
        print(f"  {'symbol':10s} {'n':>3s} {'sum':>10s} {'avg':>10s} {'non-zero':>10s}")
        out["commission_per_symbol"] = []
        for s, n, ssum, savg, nnz in comm_stats:
            print(f"  {s:10s} {n:>3d} {(ssum or 0):>10.2f} {(savg or 0):>10.4f} {nnz:>10d}")
            out["commission_per_symbol"].append({"symbol": s, "n": n, "sum": ssum, "avg": savg, "nonzero_count": nnz})

    # 4.2 Live spread sample (5 ticks per symbol, ~30s window)
    print()
    print("--- 4.2 Live spread snapshot (single tick per symbol) ---")
    out["live_spread"] = {}
    print(f"  {'symbol':8s} {'spread_pts':>10s} {'bid':>10s} {'ask':>10s}")
    for sym in SYMBOLS:
        si = mt5.symbol_info(sym)
        tick = mt5.symbol_info_tick(sym)
        if si and tick:
            spread = si.spread
            out["live_spread"][sym] = {
                "spread_points": spread,
                "bid": tick.bid, "ask": tick.ask,
                "tick_time": tick.time,
            }
            print(f"  {sym:8s} {spread:>10d} {tick.bid:>10.5f} {tick.ask:>10.5f}")

    # 4.3 Multi-tick sampling for 60s (compressed)
    print()
    print("--- 4.3 60s spread variance window (1 tick/10s, 6 samples) ---")
    out["spread_60s_window"] = {}
    samples = {sym: [] for sym in SYMBOLS}
    for i in range(6):
        for sym in SYMBOLS:
            si = mt5.symbol_info(sym)
            if si:
                samples[sym].append(si.spread)
        if i < 5:
            time.sleep(10)
    print(f"  {'symbol':8s} {'samples':>8s} {'min':>5s} {'max':>5s} {'mean':>6s}")
    for sym in SYMBOLS:
        s = samples[sym]
        if s:
            out["spread_60s_window"][sym] = {
                "samples": s, "min": min(s), "max": max(s),
                "mean": sum(s) / len(s),
            }
            print(f"  {sym:8s} {len(s):>8d} {min(s):>5d} {max(s):>5d} {sum(s)/len(s):>6.1f}")

    con.close()
    return out


def section_5():
    print()
    print("=" * 78)
    print("SECTION 5 — Swap accounting")
    print("=" * 78)
    out = {"section": 5}
    con = sqlite3.connect(TRADING_DB)
    cols = [r[1] for r in con.execute("PRAGMA table_info(trades)").fetchall()]
    has_swap = "swap" in cols
    print(f"  trades.swap column: {'YES' if has_swap else 'NO'}")
    out["has_swap_column"] = has_swap

    if has_swap:
        ssum = con.execute(
            "SELECT COUNT(*), SUM(swap), AVG(swap), SUM(CASE WHEN swap != 0 THEN 1 ELSE 0 END) "
            "FROM trades WHERE engine_version='2.4' AND open_time>='2026-04-10' AND is_closed=1"
        ).fetchone()
        n, total_swap, avg_swap, nz = ssum
        print(f"  v3 closed: n={n}, sum(swap)={total_swap:.2f}, avg={avg_swap:.4f}, nonzero={nz}")
        out["swap_v3"] = {"n": n, "sum": total_swap, "avg": avg_swap, "nonzero_count": nz}

        # Trades held > 24h
        long_held = con.execute(
            "SELECT COUNT(*) FROM trades WHERE engine_version='2.4' AND open_time>='2026-04-10' "
            "AND is_closed=1 AND (julianday(close_time) - julianday(open_time)) > 1"
        ).fetchone()[0]
        print(f"  trades held > 24h: {long_held}")
        out["trades_held_over_24h"] = long_held

    con.close()
    return out


def section_6():
    print()
    print("=" * 78)
    print("SECTION 6 — News filter")
    print("=" * 78)
    out = {"section": 6}

    con = sqlite3.connect(TRADING_DB)
    cols_t = [r[1] for r in con.execute("PRAGMA table_info(trades)").fetchall()]
    cols_sl = [r[1] for r in con.execute("PRAGMA table_info(signal_logs)").fetchall()]

    # signal_logs.status counts
    status_dist = con.execute("SELECT status, COUNT(*) FROM signal_logs GROUP BY status").fetchall()
    print(f"  signal_logs.status distribution (all-time):")
    out["signal_status_alltime"] = {}
    for s, n in status_dist:
        print(f"    {s:20s}: {n}")
        out["signal_status_alltime"][s] = n

    # v3 specifically
    print(f"  signal_logs.status (v3 only):")
    out["signal_status_v3"] = {}
    for r in con.execute("SELECT status, COUNT(*) FROM signal_logs WHERE time >= '2026-04-10' GROUP BY status").fetchall():
        s, n = r
        print(f"    {s:20s}: {n}")
        out["signal_status_v3"][s] = n

    n_news_v3 = out["signal_status_v3"].get("NEWS_FILTERED", 0)
    n_total_v3 = sum(out["signal_status_v3"].values())
    print(f"  NEWS_FILTERED in v3: {n_news_v3} of {n_total_v3} signals ({100*n_news_v3/max(n_total_v3,1):.1f}%)")

    # Find news_filter wiring
    eng = Path("engine/trading_engine.py").read_text(encoding="utf-8")
    news_check_match = re.search(r"news_blocked|NEWS_FILTERED", eng)
    has_news_filter = news_check_match is not None
    print(f"  news filter wired in engine: {has_news_filter}")
    out["news_filter_wired"] = has_news_filter

    # news_events table
    n_events = con.execute("SELECT COUNT(*) FROM news_events").fetchone()[0]
    n_high_v3 = con.execute(
        "SELECT COUNT(*) FROM news_events WHERE impact='HIGH' AND time >= '2026-04-10'"
    ).fetchone()[0]
    print(f"  news_events: {n_events} total, HIGH-impact in v3 window: {n_high_v3}")
    out["news_events_total"] = n_events
    out["news_events_high_v3"] = n_high_v3

    con.close()
    return out


def section_7():
    print()
    print("=" * 78)
    print("SECTION 7 — Structural differences + hardcoded assumptions")
    print("=" * 78)
    out = {"section": 7, "hardcoded_assumptions": []}

    # 7.3 Find hardcoded numerics that look like assumptions
    patterns = [
        (r"pip_value\s*=\s*0\.\d", "pip_value hardcoded"),
        (r"min_lot\s*=\s*0\.\d", "min_lot hardcoded"),
        (r"max_lot\s*=\s*\d+(\.\d+)?", "max_lot hardcoded"),
        (r"leverage\s*=\s*\d+", "leverage hardcoded"),
        (r"contract_size\s*=\s*\d+", "contract_size hardcoded"),
        (r"spread\s*=\s*\d+\.?\d*", "spread hardcoded"),
        (r"deviation\s*=\s*\d+", "slippage deviation hardcoded"),
    ]
    for f in [
        "engine/trading_engine.py",
        "execution/broker_adapters/mt5_adapter.py",
        "risk/manager.py" if Path("risk/manager.py").exists() else "risk/risk_manager.py",
        "scripts/paper_trade.py",
    ]:
        if not Path(f).exists():
            continue
        src = Path(f).read_text(encoding="utf-8")
        for pat, label in patterns:
            for m in re.finditer(pat, src):
                line_no = src[:m.start()].count("\n") + 1
                # Skip if it's clearly a comment or computed value
                line = src.split("\n")[line_no - 1].strip()
                if line.startswith("#"):
                    continue
                out["hardcoded_assumptions"].append({
                    "file": f, "line": line_no, "label": label, "text": line[:120]
                })

    print(f"  candidate hardcoded assumptions found: {len(out['hardcoded_assumptions'])}")
    for a in out["hardcoded_assumptions"][:10]:
        print(f"    {a['file']}:{a['line']} [{a['label']}]: {a['text']}")

    return out


def main():
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    data = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    s1 = section_1()
    data["section_1_account"] = s1
    if not s1.get("connected"):
        print("\n[STOP] cannot proceed without MT5 — skipping live sections")
    else:
        data["section_2_lot"] = section_2(s1)
        data["section_3_exec"] = section_3()
        data["section_4_spread"] = section_4(s1)
        data["section_5_swap"] = section_5()
        data["section_6_news"] = section_6()
        data["section_7_struct"] = section_7()
        try:
            mt5.shutdown()
        except Exception:
            pass

    OUT_JSON.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    print(f"\n[saved] {OUT_JSON}")


if __name__ == "__main__":
    main()
