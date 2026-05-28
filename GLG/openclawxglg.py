"""
OpenClaw x GLG — Outlook inbox monitor with AI reply draft + WhatsApp notification

Flow:
  1. Monitors Gmail inbox (Outlook emails forwarded here)
  2. When a new email arrives, Claude generates a draft reply
  3. Shows preview — you confirm y/n
  4. On confirm: prints the draft for you to copy into Outlook
                 + sends you a WhatsApp notification

Requirements (run on Windows):
  pip install anthropic pywhatkit python-dotenv

Setup:
  1. Fill in .env (copy from .env.example)
  2. Run: python openclawxglg.py
"""

import os
import imaplib
import email
import time
import json
import threading
from email.header import decode_header
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY     = os.environ["ANTHROPIC_API_KEY"]
WHATSAPP_TARGET       = os.environ["WHATSAPP_TARGET"]
EMAIL_ADDRESS         = os.environ["EMAIL_ADDRESS"]
EMAIL_PASSWORD        = os.environ["EMAIL_PASSWORD"]
IMAP_SERVER           = os.getenv("IMAP_SERVER", "imap.gmail.com")
IMAP_PORT             = int(os.getenv("IMAP_PORT", "993"))
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))
YOUR_NAME             = os.getenv("YOUR_NAME", "Aiden")

STATE_FILE = Path(__file__).parent / ".email_state.json"
LOG_FILE   = Path(__file__).parent / "openclaw_log.txt"

# ── Logging ───────────────────────────────────────────────────────────────────

def log(channel: str, recipient: str, subject: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {channel} | To: {recipient} | Subject: {subject}\n")


# ── State ─────────────────────────────────────────────────────────────────────

def load_seen() -> set:
    if STATE_FILE.exists():
        return set(json.loads(STATE_FILE.read_text()).get("seen", []))
    return set()


def save_seen(ids: set) -> None:
    STATE_FILE.write_text(json.dumps({"seen": list(ids)}))


# ── Gmail IMAP ────────────────────────────────────────────────────────────────

def decode_str(value, charset=None) -> str:
    if isinstance(value, bytes):
        return value.decode(charset or "utf-8", errors="replace")
    return value or ""


def parse_header(raw: str) -> str:
    parts = decode_header(raw or "")
    return "".join(decode_str(text, enc) for text, enc in parts)


def fetch_unseen_emails() -> list[dict]:
    with imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT) as conn:
        conn.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        conn.select("INBOX")
        _, data = conn.search(None, "UNSEEN")
        uid_list = data[0].split()
        if not uid_list:
            return []

        results = []
        for uid in uid_list:
            _, msg_data = conn.fetch(uid, "(RFC822)")
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        body = decode_str(part.get_payload(decode=True), part.get_content_charset())
                        break
            else:
                body = decode_str(msg.get_payload(decode=True), msg.get_content_charset())

            results.append({
                "uid":     uid.decode(),
                "subject": parse_header(msg.get("Subject", "(no subject)")),
                "sender":  parse_header(msg.get("From", "")),
                "date":    msg.get("Date", ""),
                "body":    body.strip(),
            })

        return results


# ── Claude reply generation ───────────────────────────────────────────────────

def generate_reply(sender: str, subject: str, body: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        messages=[{"role": "user", "content": (
            f"You are a professional assistant helping {YOUR_NAME} reply to emails.\n\n"
            f"Original email:\nFrom: {sender}\nSubject: {subject}\nBody:\n{body[:2000]}\n\n"
            f"Write a concise, professional reply. Output the reply body only — no subject line, no commentary."
        )}],
    )
    return message.content[0].text.strip()


# ── WhatsApp via pywhatkit ────────────────────────────────────────────────────

def send_whatsapp(message: str) -> None:
    try:
        import pywhatkit
    except ImportError:
        print("  pywhatkit not installed. Run: pip install pywhatkit")
        return

    result = {"error": None}

    def _send():
        try:
            pywhatkit.sendwhatmsg_instantly(
                phone_no=WHATSAPP_TARGET,
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
    elif result["error"]:
        print(f"  WhatsApp error: {result['error']}")


# ── Confirmation ──────────────────────────────────────────────────────────────

def confirm(prompt: str) -> bool:
    while True:
        answer = input(f"\n{prompt} (y/n): ").strip().lower()
        if answer in ("y", "n"):
            return answer == "y"


# ── Main loop ─────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"OpenClaw x GLG — monitoring {EMAIL_ADDRESS} every {POLL_INTERVAL_SECONDS}s.")
    print("Press Ctrl+C to stop.\n")

    seen_ids = load_seen()

    while True:
        try:
            emails = fetch_unseen_emails()
            new = [e for e in emails if e["uid"] not in seen_ids]

            for msg in new:
                print("\n" + "═" * 56)
                print(f"  From    : {msg['sender']}")
                print(f"  Subject : {msg['subject']}")
                print(f"  Date    : {msg['date']}")
                print("─" * 56)
                print(f"  Preview : {msg['body'][:300]}")
                print("─" * 56)

                print("\n  Generating reply draft with Claude...")
                reply = generate_reply(msg["sender"], msg["subject"], msg["body"])

                print("\n── Reply Draft (copy this into Outlook) " + "─" * 17)
                print(reply)
                print("─" * 56)

                if confirm("Send WhatsApp notification for this email?"):
                    whatsapp_msg = (
                        f"📧 New email from: {msg['sender']}\n"
                        f"Subject: {msg['subject']}\n\n"
                        f"Draft reply ready — check your terminal."
                    )
                    send_whatsapp(whatsapp_msg)
                    print("  WhatsApp sent.")
                    log("WHATSAPP", WHATSAPP_TARGET, msg["subject"])

                seen_ids.add(msg["uid"])
                save_seen(seen_ids)

            if not new:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] No new emails.")

        except imaplib.IMAP4.error as e:
            print(f"  IMAP error: {e}")
        except KeyboardInterrupt:
            print("\nStopped.")
            break
        except Exception as e:
            print(f"  Error: {e}")

        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
