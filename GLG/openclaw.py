"""
openclaw — outbound channel CLI for GLG PA workflow
Channels: Outlook email (win32com) and WhatsApp (pywhatkit)

Usage:
  python openclaw.py              # interactive mode
  python openclaw.py input.json   # load fields from JSON file

JSON format:
  { "recipient": "...", "subject": "...", "body": "...", "phone": "...", "message": "..." }
"""

import sys
import json
import argparse
import threading
from datetime import datetime
from pathlib import Path

LOG_FILE = Path(__file__).parent / "openclaw_log.txt"

# ── Logging ───────────────────────────────────────────────────────────────────

def log_action(channel: str, recipient: str, subject_or_preview: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{ts}] {channel} | To: {recipient} | {subject_or_preview}\n"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(entry)
    print(f"  Logged to {LOG_FILE.name}")


# ── Confirmation helper ───────────────────────────────────────────────────────

def confirm(prompt: str) -> bool:
    while True:
        answer = input(f"\n{prompt} (y/n): ").strip().lower()
        if answer in ("y", "n"):
            return answer == "y"
        print("  Please enter y or n.")


# ── Email via Outlook desktop ─────────────────────────────────────────────────

def send_email(recipient: str, subject: str, body: str) -> None:
    print("\n── Email Preview " + "─" * 40)
    print(f"  To      : {recipient}")
    print(f"  Subject : {subject}")
    print(f"  Body    :\n{body}")
    print("─" * 56)

    if not confirm("Send this email?"):
        print("  Cancelled.")
        return

    try:
        import win32com.client
    except ImportError:
        print("  Error: pywin32 is not installed. Run: pip install pywin32")
        return

    try:
        outlook = win32com.client.GetObject(Class="Outlook.Application")
    except Exception:
        print("  Outlook is not running. Please open Outlook and retry.")
        return

    try:
        mail = outlook.CreateItem(0)
        mail.To = recipient
        mail.Subject = subject
        mail.Body = body
        mail.Send()
        print("  Email sent.")
        log_action("EMAIL", recipient, f"Subject: {subject}")
    except Exception as e:
        print(f"  Failed to send email: {e}")


# ── WhatsApp via pywhatkit ────────────────────────────────────────────────────

def send_whatsapp(phone: str, message: str) -> None:
    print("\n── WhatsApp Preview " + "─" * 37)
    print(f"  To      : {phone}")
    print(f"  Message : {message}")
    print("─" * 56)

    if not confirm("Send this WhatsApp message?"):
        print("  Cancelled.")
        return

    try:
        import pywhatkit
    except ImportError:
        print("  Error: pywhatkit is not installed. Run: pip install pywhatkit")
        return

    print("  Opening WhatsApp Web (15s to load)...")

    result = {"error": None}

    def _send():
        try:
            pywhatkit.sendwhatmsg_instantly(
                phone_no=phone,
                message=message,
                wait_time=15,
                tab_close=True,
                close_time=3,
            )
        except Exception as e:
            result["error"] = e

    thread = threading.Thread(target=_send)
    thread.start()
    thread.join(timeout=20)

    if thread.is_alive():
        print("  Warning: WhatsApp Web did not respond within 20 seconds.")
        print("  The browser tab may still be loading — check manually.")
        return

    if result["error"]:
        print(f"  Failed to send WhatsApp message: {result['error']}")
        return

    print("  WhatsApp message sent.")
    log_action("WHATSAPP", phone, f"Preview: {message[:60]}")


# ── Input helpers ─────────────────────────────────────────────────────────────

def prompt_email_fields(data: dict) -> tuple[str, str, str]:
    recipient = data.get("recipient") or input("  To (email): ").strip()
    subject   = data.get("subject")   or input("  Subject   : ").strip()
    body      = data.get("body")      or input("  Body      : ").strip()
    return recipient, subject, body


def prompt_whatsapp_fields(data: dict) -> tuple[str, str]:
    phone   = data.get("phone")   or input("  To (phone with country code, e.g. +821012345678): ").strip()
    message = data.get("message") or input("  Message: ").strip()
    return phone, message


# ── Post-call follow-up ───────────────────────────────────────────────────────

CALL_OUTCOMES = {
    "1": "Could not reach him by phone; left a follow-up message. I'll chase him after an hour.",
    "2": "Could not reach him by phone again. Should I continue to chase him today?",
    "3": "Answered the call, however this project does not align with his expertise. Will proceed to decline.",
    "4": "Answered the call and is interested in the project. Will reply to the email shortly.",
}

def post_call_followup() -> None:
    print("\n── Post-Call Follow-up " + "─" * 34)
    associate = input("  Associate name (e.g. Yvette): ").strip()
    expert    = input("  Expert name (e.g. Kendall Boyd): ").strip()

    print("\n  Select call outcome:")
    print("  [1] Did not pick up — will chase after an hour")
    print("  [2] Did not pick up again — should I chase today?")
    print("  [3] Answered but doesn't align with expertise — will decline")
    print("  [4] Answered and interested — will reply to email soon")
    print("  [5] Custom — enter your own text")

    while True:
        choice = input("\n  Choice (1-5): ").strip()
        if choice in ("1", "2", "3", "4", "5"):
            break
        print("  Please enter 1-5.")

    if choice == "5":
        outcome_text = input("  Enter outcome text: ").strip()
    else:
        outcome_text = CALL_OUTCOMES[choice]

    draft = (
        f"Hi {associate},\n\n"
        f"Here is an update on the PA outreach.\n\n"
        f"1. {expert} – {outcome_text}\n\n"
        f"Best regards,\n"
        f"Aiden Lee"
    )

    print("\n── Email Draft (copy this into Outlook) " + "─" * 17)
    print(draft)
    print("─" * 56)
    log_action("POST-CALL DRAFT", associate, f"Expert: {expert} | Outcome: {choice}")


# ── Main menu ─────────────────────────────────────────────────────────────────

def main_menu() -> str:
    print("\n╔══════════════════════════════╗")
    print("║   OpenClaw — GLG PA Tool     ║")
    print("╚══════════════════════════════╝")
    print("  What do you want to do?")
    print("  [1] Send Email")
    print("  [2] Send WhatsApp")
    print("  [3] Send Both")
    print("  [4] Post-call follow-up draft")
    print("  [q] Quit")
    while True:
        choice = input("\n  Choice: ").strip().lower()
        if choice in ("1", "2", "3", "4", "q"):
            return choice
        print("  Please enter 1, 2, 3, 4, or q.")


def main() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("json_file", nargs="?", default=None)
    args = parser.parse_args()

    data: dict = {}
    if args.json_file:
        path = Path(args.json_file)
        if not path.exists():
            print(f"Error: file not found: {args.json_file}")
            sys.exit(1)
        data = json.loads(path.read_text(encoding="utf-8"))

    choice = main_menu()

    if choice == "q":
        return

    if choice == "4":
        post_call_followup()
        return

    if choice in ("1", "3"):
        print("\n── Email Details " + "─" * 40)
        recipient, subject, body = prompt_email_fields(data)
        send_email(recipient, subject, body)

    if choice in ("2", "3"):
        print("\n── WhatsApp Details " + "─" * 37)
        phone, message = prompt_whatsapp_fields(data)
        send_whatsapp(phone, message)


if __name__ == "__main__":
    main()
