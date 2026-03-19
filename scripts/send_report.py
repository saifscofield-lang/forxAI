"""Send trading performance report to Telegram bot."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from observability.telegram_notifier import TelegramNotifier


def send_report():
    notifier = TelegramNotifier()
    if not notifier.enabled:
        print("ERROR: Telegram not configured. Check .env for TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")
        return False

    report_path = os.path.join(os.path.dirname(__file__), "..", "data", "reports", "trading_report_2026-03-18.txt")

    with open(report_path, "r", encoding="utf-8") as f:
        full_report = f.read()

    # Telegram has 4096 char limit per message, split into sections
    sections = full_report.split("============================================================")
    sections = [s.strip() for s in sections if s.strip()]

    # Group sections into messages that fit under 4000 chars
    messages = []
    current_msg = ""
    for section in sections:
        candidate = current_msg + "\n\n" + section if current_msg else section
        if len(candidate) > 3900:
            if current_msg:
                messages.append(current_msg)
            current_msg = section
        else:
            current_msg = candidate
    if current_msg:
        messages.append(current_msg)

    # Send each message as pre-formatted text
    total = len(messages)
    for i, msg in enumerate(messages, 1):
        formatted = f"<pre>{msg}</pre>"
        if len(formatted) > 4096:
            # Truncate if still too long
            formatted = formatted[:4090] + "</pre>"
        success = notifier.send(formatted)
        status = "OK" if success else "FAILED"
        print(f"  Message {i}/{total}: {status} ({len(formatted)} chars)")

    print(f"\nDone! Sent {total} messages to Telegram.")
    return True


if __name__ == "__main__":
    send_report()
