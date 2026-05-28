"""
OpenClaw x GLG — GLG assignment email monitor with AI reply draft + WhatsApp drafts

Only processes emails containing a GLG streamliner consultation link.

Flow:
  1. Monitors Gmail inbox (Outlook emails forwarded here)
  2. Ignores non-GLG emails
  3. For GLG assignment emails, extracts: project, associate, note, experts (1 or many)
  4. Claude generates:
       - One reply email draft to the associate
       - One WhatsApp message draft per expert
  5. Shows all drafts in terminal for you to copy
  6. Sends you a WhatsApp notification summary

Requirements (run on Windows):
  pip install anthropic pywhatkit python-dotenv

Setup:
  1. Fill in .env
  2. Run: python openclawxglg.py
"""

import os
import re
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

STREAMLINER_RE = re.compile(
    r'https://streamliner\.glgresearch\.com/streamliner/#/consultation/\d+[^\s]*'
)

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
    conn = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
    try:
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
    finally:
        try:
            conn.logout()
        except Exception:
            pass


# ── GLG email parser ──────────────────────────────────────────────────────────

def is_glg_assignment(body: str) -> bool:
    return bool(STREAMLINER_RE.search(body))


def parse_glg_email(body: str) -> dict:
    info = {
        "project":   "",
        "associate": "",
        "note":      "",
        "link":      "",
        "experts":   [],  # list of {"name": str, "bio": str}
    }

    # Extract streamliner link
    match = STREAMLINER_RE.search(body)
    if not match:
        return info
    info["link"] = match.group(0)
    link_pos = match.end()

    # Extract project name (handles Korean, special chars, brackets)
    project_match = re.search(r"project '(.+?)'", body)
    if project_match:
        info["project"] = project_match.group(1)

    # Extract associate name and note (everything between note header and link)
    note_match = re.search(
        r"([\w][\w\s]+?) included the following note:\s*(.+?)(?=\nhttps://)",
        body, re.DOTALL
    )
    if note_match:
        info["associate"] = note_match.group(1).strip()
        info["note"] = note_match.group(2).strip()

    # Extract all experts listed after the link (one per line)
    after_link = body[link_pos:].strip()
    for line in after_link.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(" - ", 1)
        name = parts[0].strip().rstrip(" -").strip()
        bio  = parts[1].strip() if len(parts) > 1 and parts[1].strip() else ""
        if name:
            info["experts"].append({"name": name, "bio": bio})

    return info


# ── Claude generation ─────────────────────────────────────────────────────────

def generate_reply_email(info: dict) -> str:
    """One reply email to the associate."""
    import anthropic

    expert_list = "\n".join(
        f"- {e['name']}" + (f" ({e['bio']})" if e["bio"] else "")
        for e in info["experts"]
    )
    associate_first = info["associate"].split()[0] if info["associate"] else info["associate"]

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        messages=[{"role": "user", "content": (
            f"You are a professional PA assistant helping {YOUR_NAME} Lee at GLG.\n\n"
            f"Assignment details:\n"
            f"Project: {info['project']}\n"
            f"Associate: {info['associate']}\n"
            f"Associate's note: {info['note']}\n"
            f"Experts assigned:\n{expert_list}\n\n"
            f"Write a concise professional reply from {YOUR_NAME} to {info['associate']}.\n"
            f"The note may be in Korean — understand it and respond appropriately in English.\n"
            f"Acknowledge the request and confirm the action {YOUR_NAME} will take.\n"
            f"Start with 'Hi {associate_first},' and end with 'Best regards,\\n{YOUR_NAME} Lee'.\n"
            f"Output the reply body only."
        )}],
    )
    return message.content[0].text.strip()


def generate_whatsapp_draft(expert: dict, project: str, note: str) -> str:
    """One WhatsApp outreach message draft per expert."""
    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=256,
        messages=[{"role": "user", "content": (
            f"You are helping {YOUR_NAME} Lee, a PA at GLG, reach out to an expert via WhatsApp.\n\n"
            f"Expert: {expert['name']}" + (f" ({expert['bio']})" if expert["bio"] else "") + "\n"
            f"Project: {project}\n"
            f"Context from associate: {note}\n\n"
            f"Write a short, friendly WhatsApp message from {YOUR_NAME} to schedule/confirm a consultation call.\n"
            f"Keep it under 5 sentences. Output the message only."
        )}],
    )
    return message.content[0].text.strip()


# ── WhatsApp notification to Aiden ───────────────────────────────────────────

def send_whatsapp_notification(message: str) -> None:
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
    print("Only processing GLG assignment emails with a streamliner link.")
    print("Press Ctrl+C to stop.\n")

    seen_ids = load_seen()

    while True:
        try:
            emails = fetch_unseen_emails()
            new = [e for e in emails if e["uid"] not in seen_ids]

            for msg in new:
                seen_ids.add(msg["uid"])
                save_seen(seen_ids)

                if not is_glg_assignment(msg["body"]):
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Skipped (no GLG link): {msg['subject']}")
                    continue

                info = parse_glg_email(msg["body"])

                print("\n" + "═" * 60)
                print(f"  GLG Assignment Detected")
                print(f"  Project   : {info['project']}")
                print(f"  Associate : {info['associate']}")
                print(f"  Note      : {info['note']}")
                print(f"  Experts   : {len(info['experts'])}")
                for e in info["experts"]:
                    print(f"    - {e['name']}" + (f" ({e['bio']})" if e["bio"] else ""))
                print(f"  Link      : {info['link']}")
                print("─" * 60)

                print("\n  Generating reply email draft...")
                reply = generate_reply_email(info)
                print("\n── Reply Email Draft (copy into Outlook → reply to associate) " + "─" * 5)
                print(reply)
                print("─" * 60)

                print(f"\n  Generating {len(info['experts'])} WhatsApp draft(s)...")
                for i, expert in enumerate(info["experts"], 1):
                    draft = generate_whatsapp_draft(expert, info["project"], info["note"])
                    print(f"\n── WhatsApp Draft #{i} — {expert['name']} " + "─" * max(0, 40 - len(expert['name'])))
                    print(draft)
                    print("─" * 60)

                if confirm("\nSend yourself a WhatsApp summary notification?"):
                    expert_names = ", ".join(e["name"] for e in info["experts"])
                    notification = (
                        f"📋 GLG Assignment\n"
                        f"Project: {info['project']}\n"
                        f"From: {info['associate']}\n"
                        f"Experts ({len(info['experts'])}): {expert_names}\n\n"
                        f"Drafts ready — check your terminal."
                    )
                    send_whatsapp_notification(notification)
                    print("  WhatsApp notification sent.")
                    log("WHATSAPP", WHATSAPP_TARGET, msg["subject"])

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
