"""
Upload trading data to Google Drive sync folder.
Run this on the TRADING computer (the one running paper_trade.py).

Setup:
1. Install Google Drive for Desktop: https://www.google.com/drive/download/
2. Sign in with your Google account
3. Google Drive will appear as a drive letter (e.g., G:)
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

# Files to sync
FILES_TO_SYNC = [
    PROJECT_ROOT / "data" / "trading.db",
    PROJECT_ROOT / "data" / "optimized_params.yaml",
]

# Directories to sync
DIRS_TO_SYNC = [
    PROJECT_ROOT / "data" / "models",
    PROJECT_ROOT / "data" / "raw",
    PROJECT_ROOT / "data" / "logs",
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

    # Write timestamp
    marker = GDRIVE_PATH / "last_sync.txt"
    marker.write_text(f"Last upload: {timestamp}\nSource: TRADING PC\n")

    print(f"\nDone! {copied} files synced to: {GDRIVE_PATH}")
    print("Google Drive will auto-upload to cloud.")


if __name__ == "__main__":
    sync_upload()
