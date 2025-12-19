from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from pathlib import Path

from db import conn

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
            format="metadata",
            metadataHeaders=["From", "Subject"]
        ).execute()

        headers = {
            h["name"]: h["value"]
            for h in data["payload"]["headers"]
        }

        sender = extract_email(headers.get("From", ""))
        subject = headers.get("Subject", "")

        rows.append([sender, subject])
        mark_as_processed(msg_id)

    return rows
