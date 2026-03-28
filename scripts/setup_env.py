"""
Setup/Update .env file with missing variables.
Safe to run multiple times — only adds missing keys, never overwrites existing ones.

Sync this file via Google Drive, then run on trading PC:
    python scripts/setup_env.py

It will:
1. Detect if this is DEV or TRADING PC
2. Find the correct MT5 terminal path automatically
3. Find Google Drive path automatically
4. Add any missing variables to .env
"""
import os
import sys
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"

DEV_SERIAL = "T5NRSG00540121F"


def get_serial():
    try:
        r = subprocess.run(
            ["powershell", "(Get-WmiObject Win32_BIOS).SerialNumber"],
            capture_output=True, text=True, timeout=5
        )
        return r.stdout.strip()
    except Exception:
        return "UNKNOWN"


def get_machine_name(serial):
    return "DEV PC" if serial == DEV_SERIAL else "TRADING PC"


def find_mt5_path():
    """Find MetaQuotes MT5 terminal (not Deriv)."""
    candidates = [
        r"C:\Program Files\MetaTrader 5\terminal64.exe",
        r"C:\Program Files\MetaTrader 5 Terminal\terminal64.exe",
        r"C:\Program Files (x86)\MetaTrader 5\terminal64.exe",
    ]

    # Try to identify correct terminal by connecting
    try:
        import MetaTrader5 as mt5
        for path in candidates:
            if os.path.exists(path):
                if mt5.initialize(path=path):
                    info = mt5.account_info()
                    company = info.company if info else ""
                    mt5.shutdown()
                    # Skip Deriv
                    if "deriv" not in company.lower():
                        return path
                    mt5.shutdown()
    except ImportError:
        pass

    # Fallback: return first existing path
    for path in candidates:
        if os.path.exists(path):
            return path
    return ""


def find_gdrive_path():
    """Find Google Drive sync folder."""
    # Common drive letters for Google Drive
    for letter in ["G", "H", "I", "F"]:
        path = f"{letter}:/My Drive/forexAI_data"
        if os.path.exists(f"{letter}:/My Drive"):
            return path
    return ""


def read_env():
    """Read current .env file as dict."""
    env = {}
    if ENV_FILE.exists():
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    env[key.strip()] = value.strip()
    return env


def append_to_env(key, value, comment=""):
    """Append a variable to .env file."""
    with open(ENV_FILE, "a", encoding="utf-8") as f:
        if comment:
            f.write(f"\n# --- {comment} ---\n")
        f.write(f"{key}={value}\n")
    print(f"  [ADDED] {key}={value}")


def main():
    serial = get_serial()
    machine = get_machine_name(serial)

    print()
    print("=" * 55)
    print("  ForexAI — .env Setup")
    print("=" * 55)
    print(f"  Machine: {machine}")
    print(f"  Serial:  {serial}")
    print(f"  .env:    {ENV_FILE}")
    print()

    if not ENV_FILE.exists():
        print("  [ERROR] .env file not found!")
        print("  Copy .env.example to .env first, then fill MT5 credentials.")
        sys.exit(1)

    current = read_env()
    added = 0

    # ── MT5_PATH ──────────────────────────────────────────────
    if "MT5_PATH" not in current:
        print("\n[1] MT5_PATH — not set, searching...")
        mt5_path = find_mt5_path()
        if mt5_path:
            append_to_env("MT5_PATH", mt5_path, "MT5 Terminal Path (auto-detected)")
            added += 1
        else:
            print("  [WARN] Could not find MT5 terminal. Set MT5_PATH manually.")
    else:
        print(f"\n[1] MT5_PATH — OK ({current['MT5_PATH']})")

    # ── GDRIVE_SYNC_PATH ─────────────────────────────────────
    if "GDRIVE_SYNC_PATH" not in current:
        print("\n[2] GDRIVE_SYNC_PATH — not set, searching...")
        gdrive = find_gdrive_path()
        if gdrive:
            append_to_env("GDRIVE_SYNC_PATH", gdrive, "Google Drive Sync")
            added += 1
        else:
            print("  [WARN] Google Drive not found. Set GDRIVE_SYNC_PATH manually.")
    else:
        print(f"\n[2] GDRIVE_SYNC_PATH — OK ({current['GDRIVE_SYNC_PATH']})")

    # ── Summary ───────────────────────────────────────────────
    print()
    print("=" * 55)
    if added > 0:
        print(f"  Done! {added} variable(s) added to .env")
    else:
        print("  All variables already set. Nothing to do.")
    print("=" * 55)
    print()


if __name__ == "__main__":
    main()
