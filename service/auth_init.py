from google_auth_oauthlib.flow import InstalledAppFlow
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CREDENTIALS_DIR = BASE_DIR / "credentials"

CLIENT_SECRETS_FILE = CREDENTIALS_DIR / "credentials.json"
TOKEN_FILE = CREDENTIALS_DIR / "token.json"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/spreadsheets"
]


def init_google_auth():
    if not CLIENT_SECRETS_FILE.exists():
        raise FileNotFoundError(
            f"credentials.json not found at {CLIENT_SECRETS_FILE}"
        )

    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)

    flow = InstalledAppFlow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        SCOPES
    )

    creds = flow.run_local_server(port=0)

    TOKEN_FILE.write_text(
        creds.to_json(),
        encoding="utf-8"
    )

    print(f"token.json created at {TOKEN_FILE}")


if __name__ == "__main__":
    init_google_auth()
