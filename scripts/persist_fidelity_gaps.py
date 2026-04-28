"""Insert GAP-FID-* rows from the 2026-04-28 live fidelity audit.
Idempotent: skips rows whose action_id already exists."""
import sqlite3

DB = "data/improvements.db"
SOURCE = "live_fidelity_audit_2026_04_28"
TODAY = "2026-04-28"

GAPS = [
    ("GAP-FID-01", "BLOCKING", "Slippage not captured — instrument OrderSend response",
     "trade_results.slippage_pips is NULL across all 137 v3 trades. Demo broker fills at requested price; live retail will not. Required: capture slippage_pips from MT5 OrderSend response and populate per trade. Without baseline, cannot distinguish normal-vs-anomalous slippage in live.", 9),
    ("GAP-FID-02", "BLOCKING", "Commission not accounted in PnL or risk math",
     "trades.commission = 0 across all 137 v3 trades. Live broker charges per round-trip. Estimated live impact on v3 sample: -685 USD. Risk-per-trade math undercounts true cost. Pull commission from MT5 deal_info after fill.", 9),
    ("GAP-FID-03", "BLOCKING", "News filter never fired in v3 — verify wiring not broken",
     "0 NEWS_FILTERED out of 201 v3 signals despite 31 HIGH-impact events in window. Filter is wired in engine but real behavior unverified. Required: force-trigger filter on one historical HIGH event timestamp; confirm NEWS_FILTERED assignment. Untested filters fail under live load.", 9),
    ("GAP-FID-04", "BLOCKING", "Swap not captured — populate from MT5 deal history",
     "trades.swap = 0 across all 137 v3 trades, despite 7 trades held >24h. Live XAUUSD swap_short = -12.6 per night per lot. Phase 9 2k account swap drag = ~0.6%/night per held position. Capture from MT5 deal_info on close.", 9),
    ("GAP-FID-05", "BLOCKING", "Phase 9 2k lot sizing not end-to-end validated",
     "Algebraic estimate shows lot sizing should work at 2k for typical stops. But the production code path may have implicit 100k assumption. Required: run paper-trading scan with simulated 2k balance and verify lot sizes match expected math at min/typical/wide-stop edge cases.", 9),
    ("GAP-FID-06", "DOCS", "XAUUSD pip_value hardcoded 0.01 — convention muddled",
     "scripts/paper_trade.py:92 hardcodes pip_value = 0.01 for XAUUSD/JPY. Industry convention for gold pips varies. Risk-per-trade computed inconsistently between FX (1 pip = 0.0001) and XAUUSD. Replace with mt5.symbol_info(symbol).point.", None),
    ("GAP-FID-07", "MONITORING", "No requote (TRADE_RETCODE_REQUOTE 10004) handling path",
     "Engine logs requotes as errors and skips. Live broker will requote on fast markets. Demo never produced 10004 in 137 trades. Required: handle 10004 with optional retry-at-new-price OR explicit silent-skip with metric.", None),
    ("GAP-FID-08", "DOCS", "Broker server time is EEST (+3 UTC), not UTC",
     "tick.time is ~3 hours offset from datetime.now(timezone.utc). Currently this is timezone, not drift. Risk if any code compares tick.time to UTC without tz-aware conversion. Audit codebase for direct tick.time comparisons.", None),
    ("GAP-FID-09", "MONITORING", "OVERLAP-session and news-window spread regime not sampled",
     "Audit ran during off-hours (low spread). Real OVERLAP (13-17 UTC) and news-event spreads can be 2-3x higher. Required: re-run scripts/live_fidelity_audit.py during OVERLAP and during a HIGH-impact news event for regime baseline.", None),
    ("GAP-FID-10", "DOCS", "Demo leverage 1:1000 — Phase 9 broker likely 1:30-50",
     "Code has no leverage-awareness. Phase 9 retail broker (CFTC/ESMA jurisdiction) likely caps at 1:30-50. Risk math relies on max_total_risk and max_open_positions, not on leverage directly. Document the leverage assumption per Phase 9 broker selection.", None),
]

con = sqlite3.connect(DB)
cur = con.cursor()
inserted = 0
skipped = 0
try:
    con.execute("BEGIN")
    for action_id, cat, title, desc, blocking_phase in GAPS:
        existing = con.execute("SELECT 1 FROM action_items WHERE action_id=?", (action_id,)).fetchone()
        if existing:
            skipped += 1
            continue
        cur.execute("""
            INSERT INTO action_items
              (action_id, category, title, description, blocking_phase, source, created_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (action_id, cat, title, desc, blocking_phase, SOURCE, TODAY))
        inserted += 1
    con.commit()
    print(f"[OK] inserted={inserted}, skipped(existing)={skipped}")
except Exception as e:
    con.rollback()
    print(f"[FAIL] {e}")
    raise
finally:
    con.close()

# Verification
con = sqlite3.connect(DB)
print(f"total action_items: {con.execute('SELECT COUNT(*) FROM action_items').fetchone()[0]}")
print(f"GAP-FID rows      : {con.execute('SELECT COUNT(*) FROM action_items WHERE action_id LIKE ?', ('GAP-FID-%',)).fetchone()[0]}")
print(f"Phase 9 blockers  : {con.execute('SELECT COUNT(*) FROM action_items WHERE blocking_phase=9').fetchone()[0]}")
print(f"Phase 8 blockers  : {con.execute('SELECT COUNT(*) FROM action_items WHERE blocking_phase=8').fetchone()[0]}")
con.close()
