"""
Upload trading data to Google Drive sync folder.
Auto-detects DEV vs TRADING PC by serial number.

Setup:
1. Install Google Drive for Desktop: https://www.google.com/drive/download/
2. Sign in with your Google account
3. Set GDRIVE_SYNC_PATH in .env
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

# Files to sync
FILES_TO_SYNC = [
    PROJECT_ROOT / "data" / "trading.db",
    PROJECT_ROOT / "data" / "improvements.db",
    PROJECT_ROOT / "data" / "optimized_params.yaml",
    PROJECT_ROOT / "data" / "validated_params.yaml",
    PROJECT_ROOT / "config" / "base.yaml",
]

# Directories to sync
DIRS_TO_SYNC = [
    PROJECT_ROOT / "data" / "models",
    PROJECT_ROOT / "data" / "raw",
    PROJECT_ROOT / "data" / "logs",
    PROJECT_ROOT / "data" / "ml_training",
    PROJECT_ROOT / "data" / "reports",
]


def sync_upload():
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] Starting upload to Google Drive...")

    # Create sync folder
    GDRIVE_PATH.mkdir(parents=True, exist_ok=True)

    copied = 0

    # Copy individual files
    for src in FILES_TO_SYNC:
        if src.exists():
            dst = GDRIVE_PATH / src.relative_to(PROJECT_ROOT)
            dst.parent.mkdir(parents=True, exist_ok=True)

            # Only copy if source is newer
            if not dst.exists() or src.stat().st_mtime > dst.stat().st_mtime:
                shutil.copy2(src, dst)
                size_mb = src.stat().st_size / (1024 * 1024)
                print(f"  Copied: {src.name} ({size_mb:.1f} MB)")
                copied += 1
            else:
                print(f"  Skipped (unchanged): {src.name}")
        else:
            print(f"  Not found: {src}")

    # Copy directories
    for src_dir in DIRS_TO_SYNC:
        if src_dir.exists():
            dst_dir = GDRIVE_PATH / src_dir.relative_to(PROJECT_ROOT)
            file_count = 0
            for src_file in src_dir.rglob("*"):
                if src_file.is_file():
                    dst_file = dst_dir / src_file.relative_to(src_dir)
                    dst_file.parent.mkdir(parents=True, exist_ok=True)
                    if (
                        not dst_file.exists()
                        or src_file.stat().st_mtime > dst_file.stat().st_mtime
                    ):
                        shutil.copy2(src_file, dst_file)
                        file_count += 1
            if file_count:
                print(f"  Copied: {src_dir.name}/ ({file_count} files)")
                copied += file_count
            else:
                print(f"  Skipped (unchanged): {src_dir.name}/")

    # Write timestamp with machine identity
    machine = get_machine_name()
    serial = get_machine_serial()
    marker = GDRIVE_PATH / "last_sync.txt"
    marker.write_text(f"Last upload: {timestamp}\nSource: {machine}\nSerial: {serial}\n")

    print(f"\nDone! {copied} files synced to: {GDRIVE_PATH}")
    print("Google Drive will auto-upload to cloud.")


if __name__ == "__main__":
    sync_upload()
