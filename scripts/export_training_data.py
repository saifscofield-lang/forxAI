"""
Export ML Training Data from SQLite to CSV files.
Outputs to data/ml_training/ for easy access and Google Drive sync.

Usage:
    python scripts/export_training_data.py
"""
import sys
import os
import json
import sqlite3
import pandas as pd
from datetime import datetime
from pathlib import Path

sys.path.insert(0, ".")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "trading.db"
OUTPUT_DIR = PROJECT_ROOT / "data" / "ml_training"


def export_all():
    """Export all training-relevant data to CSV files."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    exported = []

    # 1. Signal logs with features expanded
    try:
        df = pd.read_sql("SELECT * FROM signal_logs ORDER BY time", conn)
        if len(df) > 0:
            # Expand features_json into columns
            if "features_json" in df.columns:
                features = df["features_json"].apply(
                    lambda x: json.loads(x) if pd.notna(x) and x else {}
                )
                feat_df = pd.DataFrame(features.tolist())
                feat_df.columns = [f"feat_{c}" for c in feat_df.columns]
                df = pd.concat([df.drop(columns=["features_json"]), feat_df], axis=1)

            path = OUTPUT_DIR / "signal_logs.csv"
            df.to_csv(path, index=False)
            exported.append(f"signal_logs: {len(df)} rows")
    except Exception as e:
        print(f"  Warning: signal_logs export failed: {e}")

    # 2. Trade results (closed trades with outcomes)
    try:
        df = pd.read_sql("SELECT * FROM trade_results ORDER BY close_time", conn)
        if len(df) > 0:
            if "features_json" in df.columns:
                features = df["features_json"].apply(
                    lambda x: json.loads(x) if pd.notna(x) and x else {}
                )
                feat_df = pd.DataFrame(features.tolist())
                feat_df.columns = [f"feat_{c}" for c in feat_df.columns]
                df = pd.concat([df.drop(columns=["features_json"]), feat_df], axis=1)

            path = OUTPUT_DIR / "trade_results.csv"
            df.to_csv(path, index=False)
            exported.append(f"trade_results: {len(df)} rows")
    except Exception as e:
        print(f"  Warning: trade_results export failed: {e}")

    # 3. Indicator snapshots (full feature vectors every scan)
    try:
        df = pd.read_sql("SELECT * FROM indicator_snapshots ORDER BY time", conn)
        if len(df) > 0:
            if "features_json" in df.columns:
                features = df["features_json"].apply(
                    lambda x: json.loads(x) if pd.notna(x) and x else {}
                )
                feat_df = pd.DataFrame(features.tolist())
                feat_df.columns = [f"feat_{c}" for c in feat_df.columns]
                df = pd.concat([df.drop(columns=["features_json"]), feat_df], axis=1)

            path = OUTPUT_DIR / "indicator_snapshots.csv"
            df.to_csv(path, index=False)
            exported.append(f"indicator_snapshots: {len(df)} rows")
    except Exception as e:
        print(f"  Warning: indicator_snapshots export failed: {e}")

    # 4. Market contexts
    try:
        df = pd.read_sql("SELECT * FROM market_contexts ORDER BY time", conn)
        if len(df) > 0:
            path = OUTPUT_DIR / "market_contexts.csv"
            df.to_csv(path, index=False)
            exported.append(f"market_contexts: {len(df)} rows")
    except Exception as e:
        print(f"  Warning: market_contexts export failed: {e}")

    # 5. Trades (open + closed)
    try:
        df = pd.read_sql("SELECT * FROM trades ORDER BY open_time", conn)
        if len(df) > 0:
            path = OUTPUT_DIR / "trades.csv"
            df.to_csv(path, index=False)
            exported.append(f"trades: {len(df)} rows")
    except Exception as e:
        print(f"  Warning: trades export failed: {e}")

    # 6. Symbol scan details
    try:
        df = pd.read_sql("SELECT * FROM symbol_scan_details ORDER BY time", conn)
        if len(df) > 0:
            path = OUTPUT_DIR / "scan_details.csv"
            df.to_csv(path, index=False)
            exported.append(f"scan_details: {len(df)} rows")
    except Exception as e:
        print(f"  Warning: scan_details export failed: {e}")

    # 7. News events
    try:
        df = pd.read_sql("SELECT * FROM news_events ORDER BY time", conn)
        if len(df) > 0:
            path = OUTPUT_DIR / "news_events.csv"
            df.to_csv(path, index=False)
            exported.append(f"news_events: {len(df)} rows")
    except Exception as e:
        print(f"  Warning: news_events export failed: {e}")

    # 8. Account snapshots
    try:
        df = pd.read_sql("SELECT * FROM account_snapshots ORDER BY time", conn)
        if len(df) > 0:
            path = OUTPUT_DIR / "account_snapshots.csv"
            df.to_csv(path, index=False)
            exported.append(f"account_snapshots: {len(df)} rows")
    except Exception as e:
        print(f"  Warning: account_snapshots export failed: {e}")

    conn.close()

    # Write export manifest
    manifest = OUTPUT_DIR / "MANIFEST.txt"
    manifest.write_text(
        f"ForexAI ML Training Data Export\n"
        f"Exported at: {timestamp}\n"
        f"Source: {DB_PATH}\n\n"
        + "\n".join(exported) + "\n"
    )

    print(f"[{timestamp}] Exported {len(exported)} datasets to {OUTPUT_DIR}")
    for item in exported:
        print(f"  {item}")


if __name__ == "__main__":
    export_all()
