"""
Project Monitor — auto-snapshot system state, track phase progress, generate status report.

Runs daily at 22:45 UTC:
  1. Snapshot system state to improvements.db
  2. Auto-advance phase steps based on conditions
  3. Detect anomalies (balance drop, win rate collapse)
  4. Generate Telegram project status report

Usage:
    from engine.project_monitor import ProjectMonitor
    monitor = ProjectMonitor(engine)
    report = monitor.run_daily()  # returns Telegram message
"""
import sqlite3
from datetime import datetime, timezone, timedelta
from loguru import logger


IMP_DB = "data/improvements.db"
TRADING_DB = "data/trading.db"

# Phase 1 start date
PHASE1_START = datetime(2026, 3, 31, tzinfo=timezone.utc)
PHASE1_PAPER_DAYS = 14  # Reduced from 30 — shadow trading covers data collection
PHASE1_MAX_DEVIATION = 0.15  # 15% paper vs backtest


class ProjectMonitor:
    """Monitor project state, auto-advance phases, generate reports."""

    def __init__(self, engine=None):
        self.engine = engine

    def run_daily(self) -> str:
        """Run all daily checks and return Telegram report."""
        state = self._collect_state()
        self._save_snapshot(state)
        self._auto_advance_steps(state)
        anomalies = self._detect_anomalies(state)
        report = self._generate_report(state, anomalies)
        return report

    def _collect_state(self) -> dict:
        """Collect current system state from all databases."""
        state = {
            "time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "current_phase": 1,
            "trading_mode": "paper",
            "balance": 0,
            "equity": 0,
            "total_trades": 0,
            "total_pnl": 0,
            "win_rate": 0,
            "open_positions": 0,
            "active_strategies": 0,
            "frozen_strategies": 0,
            "shadow_total": 0,
            "shadow_resolved": 0,
            "shadow_open": 0,
            "filter_accuracy": 0,
            "phase_steps_done": 0,
            "phase_steps_total": 0,
            "paper_day": 0,
            "paper_days_left": 0,
        }

        # Trading DB
        try:
            conn = sqlite3.connect(TRADING_DB)
            c = conn.cursor()

            # Account
            c.execute("SELECT balance, equity FROM account_snapshots ORDER BY time DESC LIMIT 1")
            row = c.fetchone()
            if row:
                state["balance"] = row[0]
                state["equity"] = row[1]

            # Trades
            c.execute("SELECT COUNT(*), SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END), SUM(profit) FROM trades WHERE is_closed = 1")
            row = c.fetchone()
            if row and row[0]:
                state["total_trades"] = row[0]
                state["total_pnl"] = row[2] or 0
                state["win_rate"] = (row[1] / row[0] * 100) if row[0] > 0 else 0

            # Open positions
            c.execute("SELECT COUNT(*) FROM trades WHERE is_closed = 0")
            state["open_positions"] = c.fetchone()[0]

            # Active strategies (distinct strategies that traded today)
            c.execute("SELECT COUNT(DISTINCT strategy) FROM trades")
            state["active_strategies"] = c.fetchone()[0]

            # Shadow signals
            c.execute("SELECT COUNT(*) FROM shadow_signals")
            state["shadow_total"] = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM shadow_signals WHERE sim_status != 'OPEN'")
            state["shadow_resolved"] = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM shadow_signals WHERE sim_status = 'OPEN'")
            state["shadow_open"] = c.fetchone()[0]

            # Filter accuracy
            c.execute("SELECT COUNT(*) FROM shadow_signals WHERE executed = 0 AND sim_status != 'OPEN'")
            blocked_total = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM shadow_signals WHERE executed = 0 AND label = 0 AND sim_status != 'OPEN'")
            blocked_correct = c.fetchone()[0]
            if blocked_total > 0:
                state["filter_accuracy"] = round(blocked_correct / blocked_total * 100, 1)

            # Circuit breaker
            c.execute("SELECT COUNT(*) FROM circuit_breaker_logs WHERE action = 'FREEZE' OR action = 'LOG_ONLY'")
            state["frozen_strategies"] = c.fetchone()[0]

            conn.close()
        except Exception as e:
            logger.error(f"Project monitor: trading DB error: {e}")

        # Phase progress from improvements DB
        try:
            conn = sqlite3.connect(IMP_DB)
            c = conn.cursor()

            c.execute("SELECT phase_number FROM project_phases WHERE status = 'IN_PROGRESS' LIMIT 1")
            row = c.fetchone()
            if row:
                state["current_phase"] = row[0]

            phase = state["current_phase"]
            c.execute("SELECT COUNT(*) FROM phase_steps WHERE phase_number = ?", (phase,))
            state["phase_steps_total"] = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM phase_steps WHERE phase_number = ? AND status = 'COMPLETED'", (phase,))
            state["phase_steps_done"] = c.fetchone()[0]

            conn.close()
        except Exception as e:
            logger.error(f"Project monitor: improvements DB error: {e}")

        # Paper trading day count
        now = datetime.now(timezone.utc)
        state["paper_day"] = max(1, (now - PHASE1_START).days + 1)
        state["paper_days_left"] = max(0, PHASE1_PAPER_DAYS - state["paper_day"])

        return state

    def _save_snapshot(self, state: dict):
        """Save state snapshot to improvements.db."""
        try:
            conn = sqlite3.connect(IMP_DB)
            conn.execute("""
                INSERT INTO system_state (
                    time, current_phase, trading_mode, active_strategies,
                    approved_strategies, total_strategies, shadow_signals_count,
                    total_trades, total_pnl, balance, win_rate, filter_accuracy,
                    open_positions, frozen_strategies, notes
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                state["time"], state["current_phase"], state["trading_mode"],
                state["active_strategies"], 0, 8, state["shadow_total"],
                state["total_trades"], state["total_pnl"], state["balance"],
                state["win_rate"], state["filter_accuracy"],
                state["open_positions"], state["frozen_strategies"],
                f"Day {state['paper_day']}/{PHASE1_PAPER_DAYS}",
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Project monitor: snapshot save error: {e}")

    def _auto_advance_steps(self, state: dict):
        """Auto-advance phase steps based on conditions."""
        try:
            conn = sqlite3.connect(IMP_DB)
            c = conn.cursor()
            phase = state["current_phase"]

            if phase == 1:
                # "Paper trade 30 days" — auto-complete when 30 days passed
                if state["paper_day"] >= PHASE1_PAPER_DAYS:
                    c.execute("""
                        UPDATE phase_steps SET status = 'COMPLETED', completed_at = ?
                        WHERE phase_number = 1 AND description LIKE '%Paper trade 30%' AND status != 'COMPLETED'
                    """, (state["time"],))

                    # Also check deviation step
                    # TODO: compare paper results vs backtest results
                    c.execute("""
                        UPDATE phase_steps SET status = 'IN_PROGRESS'
                        WHERE phase_number = 1 AND description LIKE '%deviation%' AND status = 'PENDING'
                    """)

                    if c.rowcount > 0:
                        logger.info("[PROJECT] Phase 1: 30-day paper trading complete!")

                # Check if ALL Phase 1 steps are done
                c.execute("SELECT COUNT(*) FROM phase_steps WHERE phase_number = 1 AND status != 'COMPLETED'")
                remaining = c.fetchone()[0]
                if remaining == 0:
                    c.execute("UPDATE project_phases SET status = 'COMPLETED', completed_at = ? WHERE phase_number = 1", (state["time"],))
                    c.execute("UPDATE project_phases SET status = 'IN_PROGRESS', started_at = ? WHERE phase_number = 2", (state["time"],))
                    logger.info("[PROJECT] Phase 1 COMPLETED! Phase 2 started.")

            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Project monitor: auto-advance error: {e}")

    def _detect_anomalies(self, state: dict) -> list:
        """Detect anomalies in system state."""
        anomalies = []

        # Check previous snapshot
        try:
            conn = sqlite3.connect(IMP_DB)
            c = conn.cursor()
            c.execute("SELECT balance, win_rate, total_pnl FROM system_state ORDER BY id DESC LIMIT 1 OFFSET 1")
            prev = c.fetchone()
            conn.close()

            if prev:
                prev_balance, prev_wr, prev_pnl = prev

                # Balance drop > 3% in one day
                if prev_balance > 0 and state["balance"] > 0:
                    drop_pct = (prev_balance - state["balance"]) / prev_balance * 100
                    if drop_pct > 3:
                        anomalies.append(f"Balance dropped {drop_pct:.1f}% (${prev_balance:,.0f} -> ${state['balance']:,.0f})")

                # Win rate collapse (> 10% drop)
                if prev_wr > 0 and state["win_rate"] > 0:
                    wr_drop = prev_wr - state["win_rate"]
                    if wr_drop > 10:
                        anomalies.append(f"Win rate dropped {wr_drop:.1f}% ({prev_wr:.1f}% -> {state['win_rate']:.1f}%)")

                # P&L reversal (was positive, now negative by > $1K)
                if prev_pnl > 0 and state["total_pnl"] < prev_pnl - 1000:
                    anomalies.append(f"P&L dropped ${prev_pnl - state['total_pnl']:,.0f} since yesterday")

        except Exception:
            pass

        # Filter accuracy too low
        if state["shadow_resolved"] > 20 and state["filter_accuracy"] < 40:
            anomalies.append(f"Filter accuracy low: {state['filter_accuracy']}% (filters blocking good signals)")

        return anomalies

    def _generate_report(self, state: dict, anomalies: list) -> str:
        """Generate Telegram project status report."""
        phase = state["current_phase"]
        day = state["paper_day"]
        days_left = state["paper_days_left"]
        steps_done = state["phase_steps_done"]
        steps_total = state["phase_steps_total"]

        # P&L change indicator
        pnl = state["total_pnl"]
        pnl_icon = "+" if pnl >= 0 else ""

        lines = [
            f"<b>Project Status</b> -- Phase {phase} Day {day}/{PHASE1_PAPER_DAYS}",
            "",
            f"<b>Account:</b>",
            f"  Balance: ${state['balance']:,.2f}",
            f"  P&L: {pnl_icon}${pnl:,.2f}",
            f"  Trades: {state['total_trades']} (WR {state['win_rate']:.1f}%)",
            f"  Open: {state['open_positions']}",
            "",
            f"<b>Strategies:</b>",
            f"  Active: {state['active_strategies']} / 8",
            f"  CB triggers: {state['frozen_strategies']}",
            "",
            f"<b>Shadow Trading:</b>",
            f"  Total: {state['shadow_total']} (Open: {state['shadow_open']})",
            f"  Resolved: {state['shadow_resolved']}",
            f"  Filter accuracy: {state['filter_accuracy']}%",
            "",
            f"<b>Phase {phase} Progress:</b> {steps_done}/{steps_total} steps",
        ]

        if days_left > 0:
            lines.append(f"  Paper trading: {days_left} days remaining")
        else:
            lines.append(f"  Paper trading: COMPLETE")

        if anomalies:
            lines.append("")
            lines.append("<b>Alerts:</b>")
            for a in anomalies:
                lines.append(f"  [!] {a}")

        return "\n".join(lines)
