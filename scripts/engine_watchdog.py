"""Engine watchdog (AI-018).

Monitors paper_trading.log staleness during market hours and detects when
the engine is silent (not paused, not actively scanning, not connected).

Behaviour:
  - Polls every 60 seconds.
  - Reads the last ~16 KB of paper_trading.log to determine engine state.
  - Three states: ACTIVE / PAUSED / SILENT.
  - When SILENT for >30 minutes during forex market hours, prints a clear
    alert to stdout and writes data/logs/watchdog_alerts.log.
  - DOES NOT auto-restart the engine in this v1 — manual review required.
    Auto-restart would require careful interaction with the existing
    start.bat for-loop and is deferred until the duplicate-PID issue is
    resolved (see end of file for notes).

Also detects:
  - Multiple paper_trade.py processes (current state: 4) — duplicate
    instances are reported but not killed.

Usage:
  Background-launch this from Windows Startup folder via the bundled
  setup_autostart.bat, or run manually:

      venv\\Scripts\\python.exe scripts\\engine_watchdog.py
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

LOG_PATH = Path("data/logs/paper_trading.log")
ALERT_LOG = Path("data/logs/watchdog_alerts.log")
POLL_SECONDS = 60
SILENT_THRESHOLD_MIN = 30          # >30 min without activity = SILENT
DUPLICATE_PID_THRESHOLD = 2         # >2 paper_trade.py PIDs = duplicate


def alert(msg: str) -> None:
    """Print to stdout + append to alert log."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} UTC | {msg}"
    print(line, flush=True)
    ALERT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with ALERT_LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def is_market_open(now: datetime | None = None) -> bool:
    """Forex market is closed Friday ~22:00 UTC to Sunday ~22:00 UTC."""
    now = now or datetime.now(timezone.utc)
    weekday = now.weekday()  # 0=Mon..6=Sun
    hour = now.hour
    if weekday == 5:                          # Saturday
        return False
    if weekday == 6 and hour < 22:            # Sunday before 22:00 UTC
        return False
    if weekday == 4 and hour >= 22:           # Friday after 22:00 UTC
        return False
    return True


def read_log_state() -> dict:
    """Return {marker, age_minutes, last_ts}."""
    if not LOG_PATH.exists():
        return {"marker": None, "age_min": float("inf"), "last_ts": None}
    try:
        with LOG_PATH.open("rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 16384))
            tail = f.read().decode("utf-8", errors="ignore")
    except Exception as e:
        return {"marker": "log_read_error", "age_min": float("inf"), "error": str(e), "last_ts": None}

    lines = tail.splitlines()[-300:]
    marker = None
    last_ts = None
    for line in reversed(lines):
        if "Trading paused via /pause" in line:
            marker = "paused"
        elif "Scan #" in line and ("complete" in line):
            marker = "active"
        elif "Scan #" in line and " at " in line:
            marker = "scanning"
        elif "ERROR" in line and "Shadow tracker log failed" in line:
            marker = "shadow_error"
        else:
            continue
        try:
            last_ts = datetime.strptime(line[:19], "%Y-%m-%d %H:%M:%S")
        except Exception:
            pass
        break
    if last_ts is None:
        return {"marker": marker, "age_min": float("inf"), "last_ts": None}
    age_min = (datetime.now() - last_ts).total_seconds() / 60.0
    return {"marker": marker, "age_min": age_min, "last_ts": last_ts}


def count_engine_processes() -> int:
    """Return number of running paper_trade.py python processes — scoped to
    the forexAI project path (GAP-OPS-02).

    Without the path filter, the watchdog also counts paper_trade.py in
    other Python projects on the same machine (e.g. SynthAI on Deriv has
    its own paper_trade.py). That makes the duplicate-PID alert fire
    permanently as long as both projects run. Filtering on the
    `D:\\forexAI` path in CommandLine restricts the count to this
    project's processes only."""
    try:
        result = subprocess.run(
            ["wmic", "process", "where",
             "Name='python.exe' and CommandLine like '%paper_trade.py%' "
             "and CommandLine like '%forexAI%'",
             "get", "ProcessId"],
            capture_output=True, text=True, timeout=8,
        )
        # Header is "ProcessId" + blank lines; count rows that look like PIDs
        return sum(1 for line in result.stdout.splitlines()
                   if line.strip().isdigit())
    except Exception:
        return -1


def main_loop() -> None:
    print("=" * 70)
    print("Engine Watchdog — AI-018")
    print("=" * 70)
    print(f"Watching: {LOG_PATH}")
    print(f"Alerting if silent >{SILENT_THRESHOLD_MIN}min during market hours")
    print(f"Poll interval: {POLL_SECONDS}s")
    print("Press Ctrl+C to stop.")
    print()

    last_alerted_silent = False
    last_alerted_dup = False
    while True:
        try:
            state = read_log_state()
            n_proc = count_engine_processes()
            market_open = is_market_open()

            marker = state["marker"]
            age = state["age_min"]
            ts_str = state["last_ts"].strftime("%H:%M:%S") if state["last_ts"] else "??"

            status_line = (f"[{datetime.now().strftime('%H:%M:%S')}] "
                           f"market={'open' if market_open else 'closed'} | "
                           f"engine_state={marker or 'unknown'} | "
                           f"age={age:.0f}min | "
                           f"paper_trade_pids={n_proc}")
            print(status_line, flush=True)

            # Alert: silent during market hours
            if market_open and age > SILENT_THRESHOLD_MIN and marker != "paused":
                if not last_alerted_silent:
                    alert(f"[ALERT] Engine SILENT for {age:.0f}min during market hours. "
                          f"Last log entry was {ts_str} ({marker or 'unknown'}). "
                          f"Manual investigation required.")
                    last_alerted_silent = True
            else:
                if last_alerted_silent:
                    alert(f"[RECOVERY] Engine activity resumed (marker={marker}, age={age:.0f}min).")
                    last_alerted_silent = False

            # Alert: duplicate processes
            if n_proc > DUPLICATE_PID_THRESHOLD:
                if not last_alerted_dup:
                    alert(f"[ALERT] {n_proc} paper_trade.py PIDs running (>{DUPLICATE_PID_THRESHOLD}). "
                          f"Likely duplicate engine instances from multiple start.bat launches. "
                          f"Risk: double orders to MT5. Manual cleanup recommended.")
                    last_alerted_dup = True
            else:
                if last_alerted_dup:
                    alert(f"[RECOVERY] paper_trade.py PIDs back to normal: {n_proc}.")
                    last_alerted_dup = False

            time.sleep(POLL_SECONDS)
        except KeyboardInterrupt:
            print("\n[stop] Watchdog stopped by user.")
            return
        except Exception as e:
            print(f"[error] {e}", flush=True)
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main_loop()


# ============================================================================
# AI-018 NOTES — auto-restart deferred to v2
# ============================================================================
# This watchdog is detect-and-alert only. Auto-restart would require:
#   1. Resolving the duplicate-PID issue first (currently 4 paper_trade.py
#      processes running because start.bat was launched multiple times).
#      Auto-restarting on top of duplicates makes the issue worse.
#   2. A clear shutdown signal that doesn't race with start.bat's
#      `for /L %%x in () do python paper_trade.py` infinite-restart loop.
#   3. Confirming MT5 connection state independent of paper_trading.log
#      (which is a side-effect of scans, not direct).
#
# v2 plan (separate prompt): kill orphan PIDs, add idempotent start.bat
# guard, then enable auto-restart on >30min silent during market hours.
