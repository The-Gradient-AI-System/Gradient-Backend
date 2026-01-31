from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from pathlib import Path
import base64
import json

from db import conn
from service.aiService import analyze_email

BASE_DIR = Path(__file__).resolve().parent.parent
CREDENTIALS_DIR = BASE_DIR / "credentials"
TOKEN_FILE = CREDENTIALS_DIR / "token.json"

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

_MESSAGE_VALUE_COLUMNS = [
    "status",
    "first_name",
    "last_name",
    "full_name",
    "email",
    "subject",
    "received_at",
    "company",
    "body",
    "phone",
    "website",
    "company_name",
    "company_info",
    "person_role",
    "person_links",
    "person_location",
    "person_experience",
    "person_summary",
    "person_insights",
    "company_insights",
]


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


def _store_message(gmail_id: str, values: list[str]) -> None:
    existing = conn.execute(
        "SELECT synced_at FROM gmail_messages WHERE gmail_id = ?",
        [gmail_id]
    ).fetchone()

    columns_sql = ", ".join(_MESSAGE_VALUE_COLUMNS)
    placeholders = ", ".join(["?"] * len(_MESSAGE_VALUE_COLUMNS))

    if existing is None:
        conn.execute(
            f"""
            INSERT INTO gmail_messages (gmail_id, {columns_sql})
            VALUES (?, {placeholders})
            """,
            [gmail_id, *values]
        )
    else:
        assignments = ", ".join(f"{col} = ?" for col in _MESSAGE_VALUE_COLUMNS)
        conn.execute(
            f"""
            UPDATE gmail_messages
            SET {assignments}
            WHERE gmail_id = ?
            """,
            [*values, gmail_id]
        )


def get_unsynced_message_rows(limit: int | None = None) -> list[tuple[str, list[str]]]:
    columns_sql = ", ".join(_MESSAGE_VALUE_COLUMNS)
    query = (
        f"SELECT gmail_id, {columns_sql} "
        "FROM gmail_messages "
        "WHERE synced_at IS NULL "
        "ORDER BY created_at"
    )

    if limit is not None:
        query += f" LIMIT {int(limit)}"

    rows = conn.execute(query).fetchall()

    result: list[tuple[str, list[str]]] = []
    for row in rows:
        gmail_id = row[0]
        values = [_normalize_cell(row[idx + 1]) for idx in range(len(_MESSAGE_VALUE_COLUMNS))]
        result.append((gmail_id, values))

    return result


def mark_messages_synced(gmail_ids: list[str]) -> None:
    if not gmail_ids:
        return

    placeholders = ", ".join(["?"] * len(gmail_ids))
    conn.execute(
        f"""
        UPDATE gmail_messages
        SET synced_at = CURRENT_TIMESTAMP
        WHERE gmail_id IN ({placeholders})
        """,
        gmail_ids
    )


def _normalize_cell(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value) if not isinstance(value, str) else value


def _normalize_text(text: str | None) -> str:
    if not text:
        return ""

    return text.replace("\r\n", "\n").replace("\r", "\n")


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
        
        body_original = _extract_body(payload)
        body = _normalize_text(body_original)

        parsed = analyze_email(subject=subject, body=body, sender=sender_email)

        # Prioritize name from signature/body if available
        final_sender_name = parsed.get("full_name") if parsed.get("full_name") else sender_name
        
        # Get company info if company name is available
        company_info = parsed.get("company_summary") or "No company info"
        person_summary = parsed.get("person_summary")
        first_name = parsed.get("first_name")
        last_name = parsed.get("last_name")

        person_links = parsed.get("person_links") or []
        if not isinstance(person_links, list):
            person_links = [person_links] if person_links else []
        person_links_value = json.dumps(person_links, ensure_ascii=False)

        person_insights_value = json.dumps(parsed.get("person_insights") or [], ensure_ascii=False)
        company_insights_value = json.dumps(parsed.get("company_insights") or [], ensure_ascii=False)

        row = [
            "waiting",  # status
            first_name,
            last_name,
            final_sender_name,
            sender_email,
            subject,
            formatted_date,
            parsed.get("company"),
            body,
            parsed.get("phone_number"),
            parsed.get("website"),
            parsed.get("company"),
            company_info,
            parsed.get("person_role"),
            person_links_value,
            parsed.get("person_location"),
            parsed.get("person_experience"),
            person_summary,
            person_insights_value,
            company_insights_value,
        ]

        rows.append(row)
        _store_message(msg_id, row)
        mark_as_processed(msg_id)

    return rows

