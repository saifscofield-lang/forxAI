"""
Download trading data from Google Drive sync folder.
Run this on the DEV computer to pull latest data from the trading PC.

Setup:
1. Install Google Drive for Desktop: https://www.google.com/drive/download/
2. Sign in with the SAME Google account used on the trading PC
3. Google Drive will appear as a drive letter (e.g., G:\)
4. Update GDRIVE_PATH below if your drive letter is different
"""

import sys
import shutil
import os
from pathlib import Path
from datetime import datetime

sys.path.insert(0, ".")

# === CONFIGURATION ===
PROJECT_ROOT = Path(__file__).resolve().parent.parent
GDRIVE_PATH = Path(os.getenv("GDRIVE_SYNC_PATH", "G:/My Drive/forexAI_data"))


def sync_download():
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] Downloading data from Google Drive...")

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
