"""
OpenClaw x GLG — GLG assignment email monitor

Flow:
  1. Monitors Gmail inbox (Outlook emails forwarded here)
  2. Ignores non-GLG emails
  3. For GLG assignment emails:
       - Parses project, associate, note, experts
       - For each expert: ask call outcome (4 options + custom)
       - Generates ONE reply email in associate's language (Korean/English)
       - For each expert: choose WhatsApp template (general / scheduling / custom)
       - Shows all drafts to copy

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
YOUR_NAME_KO          = os.getenv("YOUR_NAME_KO", "이현구")

STREAMLINER_RE = re.compile(
    r'https://streamliner\.glgresearch\.com/streamliner/#/consultation/\d+[^\s]*'
)

STATE_FILE = Path(__file__).parent / ".email_state.json"
LOG_FILE   = Path(__file__).parent / "openclaw_log.txt"

# ── Call outcome options (English + Korean) ───────────────────────────────────

OUTCOMES_EN = {
    "1": "Could not reach him by phone; left a follow-up message. Will chase after an hour.",
    "2": "Could not reach him by phone again. Should I continue to chase him today?",
    "3": "Answered the call, however this project does not align with his expertise. Will proceed to decline.",
    "4": "Answered the call and is interested in the project. Will reply to the email shortly.",
}

OUTCOMES_KO = {
    "1": "현재 연락을 안 받으셔서 메세지 보내드리고 1시간 이후에 Chase 진행하겠습니다.",
    "2": "다시 연락을 드렸으나 받지 않으셨습니다. 오늘 추가로 연락을 드려야 할까요?",
    "3": "통화를 하셨으나 이번 프로젝트와 전문 분야가 맞지 않아 거절 진행하겠습니다.",
    "4": "연락 받으셨고 프로젝트에 관심을 보이셨습니다. 곧 이메일로 회신 드리겠습니다.",
}

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


def is_valid_expert_line(line: str) -> bool:
    """Filter out garbage lines after the link (ref:, legal text, blank, URLs)."""
    line = line.strip()
    if not line:
        return False
    if line.lower().startswith("ref:"):
        return False
    if line.lower().startswith("this e-mail") or line.lower().startswith("this email"):
        return False
    if line.startswith("http"):
        return False
    if len(line) > 300:
        return False
    return True


def clean_expert_name(name: str) -> str:
    """Strip leading number prefix like '1. ' or '2. '."""
    return re.sub(r'^\d+\.\s*', '', name).strip().rstrip(" -").strip()


def parse_glg_email(body: str) -> dict:
    info = {
        "project":   "",
        "associate": "",
        "note":      "",
        "link":      "",
        "experts":   [],
    }

    match = STREAMLINER_RE.search(body)
    if not match:
        return info
    info["link"] = match.group(0)
    link_pos = match.end()

    project_match = re.search(r"project '(.+?)'", body)
    if project_match:
        info["project"] = project_match.group(1)

    note_match = re.search(
        r"([\w][\w\s]+?) included the following note:\s*(.+?)(?=\nhttps://)",
        body, re.DOTALL
    )
    if note_match:
        info["associate"] = note_match.group(1).strip()
        info["note"] = note_match.group(2).strip()

    after_link = body[link_pos:].strip()
    for line in after_link.splitlines():
        if not is_valid_expert_line(line):
            continue
        parts = line.split(" - ", 1)
        name = clean_expert_name(parts[0])
        bio  = parts[1].strip() if len(parts) > 1 and parts[1].strip() else ""
        if name:
            info["experts"].append({"name": name, "bio": bio})

    return info


def is_korean(text: str) -> bool:
    return bool(re.search(r'[가-힣]', text))


# ── Reply email builder ───────────────────────────────────────────────────────

def build_reply_email(info: dict, expert_outcomes: list[dict]) -> str:
    """Build structured reply email. Language matches associate's note."""
    korean = is_korean(info["note"])
    # Use everything except the last word (last name) as the first name
    parts = info["associate"].split()
    associate_first = " ".join(parts[:-1]) if len(parts) > 1 else parts[0]

    if korean:
        lines = [f"안녕하세요 {associate_first}님,\n", "PA 진행 결과를 보고드립니다."]
        for i, eo in enumerate(expert_outcomes, 1):
            lines.append(f"{i}. {eo['name']} - {eo['outcome']}")
        lines += ["\n감사합니다.", f"{YOUR_NAME_KO} 드림"]
    else:
        lines = [f"Hi {associate_first},\n", "Here is an update on the PA outreach."]
        for i, eo in enumerate(expert_outcomes, 1):
            lines.append(f"{i}. {eo['name']} – {eo['outcome']}")
        lines += ["\nBest regards,", f"{YOUR_NAME} Lee"]

    return "\n".join(lines)


# ── WhatsApp template builder ─────────────────────────────────────────────────

def build_whatsapp_general(expert_name: str, project: str) -> str:
    first = expert_name.split()[0]
    return (
        f"Hello {first}, this is {YOUR_NAME} Lee from GLG Korea (Gerson Lehrman Group).\n\n"
        f"I hope you're doing well! We recently sent you an email regarding a research project on "
        f"\"{project}\". We believe your insights would be extremely valuable for this project.\n\n"
        f"Would you happen to be interested in sharing your perspective? If so, could you check your "
        f"inbox at your earliest convenience and let us know your thoughts?\n\n"
        f"Please feel free to reply here if that's easier. Thank you, and have a great day!\n\n"
        f"Best,\n{YOUR_NAME} Lee | GLG Korea"
    )


def build_whatsapp_scheduling(expert_name: str, project: str, slots: list[str]) -> str:
    slot_lines = "\n".join(f"[Time]: {s}" for s in slots)
    return (
        f"Hello {expert_name},\n"
        f"This is {YOUR_NAME} Lee from GLG Korea.\n\n"
        f"Thank you again for your willingness to cooperate on the project regarding \"{project}\". "
        f"Your expert insights are a valuable contribution to our clients.\n\n"
        f"In order to move forward with the consultation process, we would like to ask for your "
        f"availability within the following times:\n"
        f"{slot_lines}\n\n"
        f"Please let us know if you have any questions or would like additional information.\n\n"
        f"Thank you for your time.\n\n"
        f"Best regards,\n{YOUR_NAME} Lee | GLG Korea"
    )


# ── WhatsApp sending ──────────────────────────────────────────────────────────

def send_whatsapp_to(phone: str, message: str) -> None:
    """Send WhatsApp message to a specific number."""
    try:
        import pywhatkit
    except ImportError:
        print("  pywhatkit not installed. Run: pip install pywhatkit")
        return

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
    elif result["error"]:
        print(f"  WhatsApp error: {result['error']}")


# ── WhatsApp notification to Aiden ────────────────────────────────────────────

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


# ── Interactive prompts ───────────────────────────────────────────────────────

def confirm(prompt: str) -> bool:
    while True:
        answer = input(f"\n{prompt} (y/n): ").strip().lower()
        if answer in ("y", "n"):
            return answer == "y"


def pick_outcome(expert_name: str, korean: bool) -> str:
    outcomes = OUTCOMES_KO if korean else OUTCOMES_EN
    print(f"\n  Call outcome for {expert_name}:")
    print("  [1] Did not pick up — will chase after an hour")
    print("  [2] Did not pick up again — should I chase today?")
    print("  [3] Answered but doesn't align — will decline")
    print("  [4] Answered and interested — will reply soon")
    print("  [5] Custom — enter your own text")
    while True:
        choice = input("  Choice (1-5): ").strip()
        if choice in ("1", "2", "3", "4"):
            return outcomes[choice]
        if choice == "5":
            return input("  Enter outcome text: ").strip()
        print("  Please enter 1-5.")


def pick_whatsapp_template(expert: dict, project: str) -> tuple[str, str]:
    """Returns (phone, message). Prompts for phone number then sends automatically."""
    print(f"\n  WhatsApp for {expert['name']}:")
    print("  [1] General PA outreach (ask expert to check inbox)")
    print("  [2] Scheduling request (ask for availability with time slots)")
    print("  [3] Custom — type your own message")
    print("  [s] Skip — don't send WhatsApp to this expert")
    while True:
        choice = input("  Choice (1-3 / s): ").strip().lower()
        if choice == "s":
            return "", ""
        if choice == "1":
            message = build_whatsapp_general(expert["name"], project)
            break
        if choice == "2":
            slots = []
            print("  Enter time slots one per line (press Enter twice when done):")
            while True:
                slot = input("    Slot: ").strip()
                if not slot:
                    break
                slots.append(slot)
            message = build_whatsapp_scheduling(expert["name"], project, slots)
            break
        if choice == "3":
            message = input("  Enter your message: ").strip()
            break
        print("  Please enter 1-3 or s.")

    print(f"\n── WhatsApp Draft — {expert['name']} " + "─" * max(0, 42 - len(expert['name'])))
    print(message)
    print("─" * 60)

    phone = input(f"  Enter {expert['name']}'s WhatsApp number (e.g. +821012345678): ").strip()
    return phone, message


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
                korean = is_korean(info["note"])

                print("\n" + "═" * 60)
                print(f"  GLG Assignment Detected")
                print(f"  Project   : {info['project']}")
                print(f"  Associate : {info['associate']} ({'Korean' if korean else 'English'})")
                print(f"  Note      : {info['note']}")
                print(f"  Experts   : {len(info['experts'])}")
                for e in info["experts"]:
                    print(f"    - {e['name']}" + (f" ({e['bio'][:60]}...)" if len(e.get('bio','')) > 60 else (f" ({e['bio']})" if e.get('bio') else "")))
                print("─" * 60)

                # Collect outcome per expert
                expert_outcomes = []
                for expert in info["experts"]:
                    outcome = pick_outcome(expert["name"], korean)
                    expert_outcomes.append({"name": expert["name"], "outcome": outcome})

                # Build and show reply email
                reply = build_reply_email(info, expert_outcomes)
                print("\n── Reply Email Draft (copy into Outlook → reply to associate) " + "─" * 5)
                print(reply)
                print("─" * 60)

                # Send WhatsApp per expert
                for expert in info["experts"]:
                    phone, message = pick_whatsapp_template(expert, info["project"])
                    if phone and message:
                        print(f"  Sending WhatsApp to {expert['name']} ({phone})...")
                        send_whatsapp_to(phone, message)
                        print(f"  Sent.")
                        log("WHATSAPP", phone, f"{expert['name']} — {info['subject'] if 'subject' in info else info['project']}")

                # Send notification to Aiden's WhatsApp
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
