from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from pathlib import Path
import base64
import json

from concurrent.futures import ThreadPoolExecutor

from db import conn, save_cached_replies
from service.aiService import analyze_email, preprocess_email, generate_email_replies_six

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
    "is_lead",
    "priority",
    "status_label",
    "tone",
    "preprocessed_at",
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


def _update_stage1(gmail_id: str, stage1_result: dict) -> None:
    """Оновлює рядок після Етапу 1 (пре-процесинг): is_lead, priority, status_label, tone, preprocessed_at."""
    sender_name = stage1_result.get("sender_name") or ""
    is_lead = stage1_result.get("is_lead", False)
    priority = stage1_result.get("priority") or "normal"
    status_label = stage1_result.get("status_label") or ""
    tone = stage1_result.get("tone") or ""

    conn.execute(
        """
        UPDATE gmail_messages
        SET full_name = COALESCE(NULLIF(?, ''), full_name),
            is_lead = ?,
            priority = ?,
            status_label = ?,
            tone = ?,
            preprocessed_at = CURRENT_TIMESTAMP
        WHERE gmail_id = ?
        """,
        [sender_name, is_lead, priority, status_label, tone, gmail_id],
    )


_preprocess_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="preprocess")


def _run_stage1_then_update(gmail_id: str, subject: str, body: str, sender_email: str) -> None:
    try:
        result = preprocess_email(subject=subject, body=body, sender=sender_email)
        _update_stage1(gmail_id, result)
        _preprocess_executor.submit(_run_pregen_replies, gmail_id)
        _preprocess_executor.submit(_run_analyze_email, gmail_id)
    except Exception as e:
        print(f"[gmailService] Stage 1 failed for {gmail_id[:12]}...: {e}")


def _run_pregen_replies(gmail_id: str) -> None:
    """У фоні генерує 6 варіантів відповіді та зберігає в кеш після Етапу 1."""
    try:
        row = conn.execute(
            f"SELECT {', '.join(_MESSAGE_VALUE_COLUMNS)} FROM gmail_messages WHERE gmail_id = ?",
            [gmail_id],
        ).fetchone()
        if not row:
            return
        lead = dict(zip(_MESSAGE_VALUE_COLUMNS, (_normalize_cell(v) for v in row)))
        email = {
            "sender": lead.get("email") or "",
            "subject": lead.get("subject") or "",
            "body": lead.get("body") or "",
        }
        email_key = (lead.get("email") or "").strip()
        subject_key = (lead.get("subject") or "").strip()
        received_at_key = (lead.get("received_at") or "").strip()
        if not email_key or not subject_key or not received_at_key:
            return
        replies = generate_email_replies_six(
            lead=lead,
            email=email,
            tone=lead.get("tone"),
        )
        save_cached_replies(email_key, subject_key, received_at_key, replies)
    except Exception as e:
        print(f"[gmailService] Pregen replies failed for {gmail_id[:12]}...: {e}")


def _run_analyze_email(gmail_id: str) -> None:
    """У фоні викликає analyze_email та оновлює рядок у gmail_messages (контакт, компанія, телефон тощо). Після цього рядок готовий до синхронізації в Sheets."""
    try:
        row = conn.execute(
            "SELECT body, subject, email FROM gmail_messages WHERE gmail_id = ?",
            [gmail_id],
        ).fetchone()
        if not row:
            return
        body, subject, sender = (_normalize_cell(v) for v in row)
        if not (body or subject):
            return
        result = analyze_email(subject=subject or "", body=body or "", sender=sender or "")
        person_links = result.get("person_links") or []
        person_insights = result.get("person_insights") or []
        company_insights = result.get("company_insights") or []
        conn.execute(
            """
            UPDATE gmail_messages
            SET first_name = ?, last_name = ?, full_name = ?, company = ?, phone = ?,
                website = ?, company_name = ?, company_info = ?, person_role = ?,
                person_links = ?, person_location = ?, person_experience = ?, person_summary = ?,
                person_insights = ?, company_insights = ?, analyzed_at = CURRENT_TIMESTAMP
            WHERE gmail_id = ?
            """,
            [
                result.get("first_name") or "",
                result.get("last_name") or "",
                result.get("full_name") or "",
                result.get("company") or "",
                result.get("phone_number") or "",
                result.get("website") or "",
                result.get("company") or "",
                result.get("company_summary") or "",
                result.get("person_role") or "",
                json.dumps(person_links, ensure_ascii=False) if person_links else "",
                result.get("person_location") or "",
                result.get("person_experience") or "",
                result.get("person_summary") or "",
                json.dumps(person_insights, ensure_ascii=False) if person_insights else "",
                json.dumps(company_insights, ensure_ascii=False) if company_insights else "",
                gmail_id,
            ],
        )
    except Exception as e:
        print(f"[gmailService] Analyze email failed for {gmail_id[:12]}...: {e}")
        # Щоб рядок не залишався без analyzed_at і міг потрапити в майбутні вибірки за потреби
        try:
            conn.execute(
                "UPDATE gmail_messages SET analyzed_at = CURRENT_TIMESTAMP WHERE gmail_id = ?",
                [gmail_id],
            )
        except Exception:
            pass


def get_unsynced_message_rows(limit: int | None = None) -> list[tuple[str, list[str]]]:
    """Повертає листи, які вже проаналізовані (analyzed_at) і ще не в Sheets. У CRM лист з'являється готовим: з інфою + кешем відповідей, без очікування.
    Синхронізуємо одразу після Stage 1, щоб лист з’явився в UI; analyze_email заповнює дані у фоні."""
    columns_sql = ", ".join(_MESSAGE_VALUE_COLUMNS)
    query = (
        f"SELECT gmail_id, {columns_sql} "
        "FROM gmail_messages "
        "WHERE synced_at IS NULL AND preprocessed_at IS NOT NULL AND analyzed_at IS NOT NULL "
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
    if isinstance(value, bool):
        return "true" if value else "false"
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

        # Етап 1: зберігаємо сирий лист одразу, пре-процесинг (is_lead, priority, tone) — у фоні
        raw_row = [
            "waiting",
            "",
            "",
            sender_name or "",
            sender_email,
            subject,
            formatted_date,
            "",
            body,
            "", "", "", "", "",
            "[]",
            "", "", "",
            "[]",
            "[]",
            False,
            "normal",
            "",
            "",
            None,
        ]
        _store_message(msg_id, raw_row)
        mark_as_processed(msg_id)
        rows.append(raw_row)

        # Фонова задача: Етап 1 (preprocess_email) → оновлення рядка
        _preprocess_executor.submit(_run_stage1_then_update, msg_id, subject, body, sender_email)

    return rows

