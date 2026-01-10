from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from pathlib import Path
import base64

from db import conn
from service.aiService import analyze_email

BASE_DIR = Path(__file__).resolve().parent.parent
CREDENTIALS_DIR = BASE_DIR / "credentials"
TOKEN_FILE = CREDENTIALS_DIR / "token.json"

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def get_gmail_service():
    if not TOKEN_FILE.exists():
        raise FileNotFoundError(
            f"token.json not found at {TOKEN_FILE}. "
            "Authorize Gmail first."
        )

    creds = Credentials.from_authorized_user_file(
        TOKEN_FILE,
        SCOPES
    )
    return build("gmail", "v1", credentials=creds)


def is_processed(msg_id: str) -> bool:
    result = conn.execute(
        "SELECT 1 FROM processed_emails WHERE gmail_id = ?",
        [msg_id]
    ).fetchone()
    return result is not None


def mark_as_processed(msg_id: str):
    conn.execute(
        "INSERT OR IGNORE INTO processed_emails (gmail_id) VALUES (?)",
        [msg_id]
    )


def extract_email(from_header: str) -> str:
    if "<" in from_header:
        return from_header.split("<")[1].replace(">", "").strip()
    return from_header.strip()


def _decode_body(data: str) -> str:
    if not data:
        return ""

    try:
        # Gmail API returns base64url encoded data
        decoded_bytes = base64.urlsafe_b64decode(data.encode("utf-8"))
        return decoded_bytes.decode("utf-8", errors="replace")
    except Exception:
        return ""


def _extract_body(payload: dict) -> str:
    """Extract plain text body from Gmail message payload."""
    if not payload:
        return ""

    # Multipart message
    parts = payload.get("parts") or []
    if parts:
        # Prefer text/plain
        for part in parts:
            mime = part.get("mimeType", "")
            if mime == "text/plain":
                body = part.get("body", {}).get("data", "")
                text = _decode_body(body)
                if text:
                    return text

        # Fallback: first part with any data
        for part in parts:
            body = part.get("body", {}).get("data", "")
            text = _decode_body(body)
            if text:
                return text

    # Non-multipart
    body = payload.get("body", {}).get("data", "")
    return _decode_body(body)



def fetch_new_gmail_data(limit: int = 20):
    service = get_gmail_service()

    messages = service.users().messages().list(
        userId="me",
        labelIds=["INBOX"],
        maxResults=limit
    ).execute().get("messages", [])

    rows = []

    for msg in messages:
        msg_id = msg["id"]

        if is_processed(msg_id):
            continue

        data = service.users().messages().get(
            userId="me",
            id=msg_id,
            format="full",
            metadataHeaders=["From", "Subject", "Date", "To"]
        ).execute()

        payload = data.get("payload", {})
        headers = {
            h["name"]: h["value"]
            for h in payload.get("headers", [])
        }

        from_header = headers.get("From", "")
        sender_email = extract_email(from_header)
        sender_name = from_header.split("<")[0].strip() if "<" in from_header else ""
        
        subject = headers.get("Subject", "")
        
        # Parse and format date
        date_str = headers.get("Date", "")
        formatted_date = date_str
        try:
            from email.utils import parsedate_to_datetime
            if date_str:
                dt = parsedate_to_datetime(date_str)
                formatted_date = dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass

        recipient = headers.get("To", "")
        
        body = _extract_body(payload)

        parsed = analyze_email(subject=subject, body=body, sender=sender_email)

        # Prioritize name from signature/body if available
        final_sender_name = parsed.get("full_name") if parsed.get("full_name") else sender_name
        
        # Get company info if company name is available
        company_info = parsed.get("company_summary") or "No company info"

        row = [
            final_sender_name,
            sender_email,
            subject,
            formatted_date,
            parsed.get("company"),  # Index 4: Company header
            body,
            parsed.get("phone_number"),
            parsed.get("website"),
            parsed.get("company"),  # Index 8: Company Name header
            company_info,  # Company Info from scraper
        ]

        rows.append(row)
        mark_as_processed(msg_id)

    return rows

