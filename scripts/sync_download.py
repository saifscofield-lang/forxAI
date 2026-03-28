"""
Download trading data from Google Drive sync folder.
Auto-detects DEV vs TRADING PC by serial number.

Setup:
1. Install Google Drive for Desktop
2. Set GDRIVE_SYNC_PATH in .env
"""

import sys
import shutil
import os
import subprocess
from pathlib import Path
from datetime import datetime

sys.path.insert(0, ".")

# === Machine Identity ===
DEV_SERIAL = "T5NRSG00540121F"


def get_machine_serial():
    """Get this machine's serial number."""
    try:
        result = subprocess.run(
            ["powershell", "(Get-WmiObject Win32_BIOS).SerialNumber"],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip()
    except Exception:
        return "UNKNOWN"


def get_machine_name():
    """Return 'DEV PC' or 'TRADING PC' based on serial."""
    serial = get_machine_serial()
    return "DEV PC" if serial == DEV_SERIAL else "TRADING PC"

# === CONFIGURATION ===
PROJECT_ROOT = Path(__file__).resolve().parent.parent
GDRIVE_PATH = Path(os.getenv("GDRIVE_SYNC_PATH", "G:/My Drive/forexAI_data"))


def sync_download():
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    machine = get_machine_name()
    print(f"[{timestamp}] Downloading data from Google Drive...")
    print(f"  This machine: {machine} (Serial: {get_machine_serial()})")

    if not GDRIVE_PATH.exists():
        print(f"ERROR: Google Drive folder not found: {GDRIVE_PATH}")
        print("Make sure Google Drive for Desktop is installed and synced.")
        print("Or set GDRIVE_SYNC_PATH environment variable.")
        sys.exit(1)

    # Check last sync time
    marker = GDRIVE_PATH / "last_sync.txt"
    if marker.exists():
        print(f"  {marker.read_text().strip()}")
        print()

    copied = 0

    # Copy everything from Google Drive to project
    for src_file in GDRIVE_PATH.rglob("*"):
        if src_file.is_file() and src_file.name != "last_sync.txt":
            rel_path = src_file.relative_to(GDRIVE_PATH)
            dst_file = PROJECT_ROOT / rel_path
            dst_file.parent.mkdir(parents=True, exist_ok=True)

            # Only copy if source is newer
            if (
                not dst_file.exists()
                or src_file.stat().st_mtime > dst_file.stat().st_mtime
            ):
                shutil.copy2(src_file, dst_file)
                size_mb = src_file.stat().st_size / (1024 * 1024)
                print(f"  Downloaded: {rel_path} ({size_mb:.2f} MB)")
                copied += 1

    if copied:
        print(f"\nDone! {copied} files downloaded to: {PROJECT_ROOT / 'data'}")
    else:
        print("\nNo new data to download. Everything is up to date.")


if __name__ == "__main__":
    sync_download()
