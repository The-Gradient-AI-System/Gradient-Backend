from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
PROCESSED_FILE = Path("db/processed_ids.txt")

def get_gmail_service():
    creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    return build("gmail", "v1", credentials=creds)

def load_processed_ids() -> set:
    if not PROCESSED_FILE.exists():
        return set()
    return set(PROCESSED_FILE.read_text().splitlines())

def save_processed_id(msg_id: str):
    PROCESSED_FILE.parent.mkdir(exist_ok=True)
    with PROCESSED_FILE.open("a") as f:
        f.write(msg_id + "\n")

def extract_email(from_header: str) -> str:
    if "<" in from_header:
        return from_header.split("<")[1].replace(">", "").strip()
    return from_header.strip()

def fetch_new_gmail_data(limit: int = 20):
    service = get_gmail_service()
    processed_ids = load_processed_ids()

    messages = service.users().messages().list(
        userId="me",
        labelIds=["INBOX"],
        maxResults=limit
    ).execute().get("messages", [])

    rows = []

    for msg in messages:
        msg_id = msg["id"]
        if msg_id in processed_ids:
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
        save_processed_id(msg_id)

    return rows
