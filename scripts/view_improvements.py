"""
عرض قاعدة بيانات التحسينات — View Improvements Database
Usage:
    python scripts/view_improvements.py              # All pending/partial
    python scripts/view_improvements.py --all        # Everything
    python scripts/view_improvements.py --status DONE
    python scripts/view_improvements.py --priority CRITICAL
    python scripts/view_improvements.py --next       # What to do next
"""
import sys
sys.path.insert(0, ".")

import sys as _sys, io
_sys.stdout = io.TextIOWrapper(_sys.stdout.buffer, encoding='utf-8')

import sqlite3
import argparse

DB_PATH = "data/improvements.db"

PRIORITY_EMOJI = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🔵"}
STATUS_EMOJI = {"DONE": "✅", "PARTIAL": "🔶", "PENDING": "⬜", "SKIPPED": "⏭️", "IN_PROGRESS": "🔧"}


def view(filter_status=None, filter_priority=None, show_all=False, show_next=False):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    if show_next:
        # Show actionable items in priority order
        c.execute("""
            SELECT * FROM improvements
            WHERE status IN ('PENDING', 'PARTIAL')
            ORDER BY
                CASE priority WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2
                              WHEN 'MEDIUM' THEN 3 WHEN 'LOW' THEN 4 END,
                code
        """)
    elif filter_status:
        c.execute("SELECT * FROM improvements WHERE status = ? ORDER BY code", (filter_status,))
    elif filter_priority:
        c.execute("SELECT * FROM improvements WHERE priority = ? ORDER BY code", (filter_priority,))
    elif show_all:
        c.execute("SELECT * FROM improvements ORDER BY code")
    else:
        c.execute("SELECT * FROM improvements WHERE status NOT IN ('DONE', 'SKIPPED') ORDER BY code")

    rows = c.fetchall()

    if not rows:
        print("No improvements found matching criteria.")
        return

    for row in rows:
        p = PRIORITY_EMOJI.get(row["priority"], "  ")
        s = STATUS_EMOJI.get(row["status"], "  ")
        print(f"\n{p} {row['code']} [{row['status']}] {row['title']}")
        if row["title_ar"]:
            print(f"   {row['title_ar']}")
        print(f"   Category: {row['category']} | Priority: {row['priority']}")
        print(f"   Problem:  {row['problem'][:120]}...")
        if show_next or show_all:
            sol_lines = row["solution"].split("\n")
            print(f"   Solution: {sol_lines[0]}")
            for line in sol_lines[1:4]:
                print(f"             {line}")
        if row["depends_on"] and row["depends_on"] != "[]":
            print(f"   Depends:  {row['depends_on']}")
        if row["notes"]:
            print(f"   Notes:    {row['notes'][:120]}")

    print(f"\n--- Total: {len(rows)} improvements ---")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--status", type=str)
    parser.add_argument("--priority", type=str)
    parser.add_argument("--next", action="store_true")
    args = parser.parse_args()

    view(
        filter_status=args.status.upper() if args.status else None,
        filter_priority=args.priority.upper() if args.priority else None,
        show_all=args.all,
        show_next=args.next,
    )
