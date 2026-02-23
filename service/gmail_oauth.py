"""
Web OAuth flow for Gmail/Sheets: user logs in in browser, we save token.json.
Requires GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, BACKEND_URL in env.
In Google Cloud Console add redirect URI: {BACKEND_URL}/gmail/oauth2callback
"""
import os
from pathlib import Path

from google_auth_oauthlib.flow import Flow

_BASE_DIR = Path(__file__).resolve().parent.parent
_CREDENTIALS_DIR = _BASE_DIR / "credentials"
_TOKEN_FILE = _CREDENTIALS_DIR / "token.json"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/spreadsheets",
]

# In-memory: state -> flow (for callback). Single instance only.
_pending_flows: dict[str, Flow] = {}


def _client_config():
    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        return None
    base_url = (os.getenv("BACKEND_URL") or "").strip().rstrip("/")
    if not base_url:
        return None
    redirect_uri = f"{base_url}/gmail/oauth2callback"
    return {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uris": [redirect_uri],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }


def get_authorization_url():
    """Returns (redirect_url, None) or (None, error_message)."""
    config = _client_config()
    if not config:
        return None, "Set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, BACKEND_URL in Environment."
    base_url = (os.getenv("BACKEND_URL") or "").strip().rstrip("/")
    redirect_uri = f"{base_url}/gmail/oauth2callback"
    try:
        flow = Flow.from_client_config(
            config,
            scopes=SCOPES,
            redirect_uri=redirect_uri,
        )
        auth_url, state = flow.authorization_url(
            access_type="offline",
            prompt="consent",
            include_granted_scopes="true",
        )
        _pending_flows[state] = flow
        return auth_url, None
    except Exception as e:
        return None, str(e)


def exchange_code_and_save_token(code: str, state: str) -> tuple[bool, str]:
    """
    Exchange code for token, save to token.json.
    Returns (success, message_or_error).
    """
    flow = _pending_flows.pop(state, None)
    if not flow:
        return False, "Invalid or expired state. Start again from /gmail/auth"
    try:
        flow.fetch_token(code=code)
        creds = flow.credentials
        _CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
        _TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
        return True, "Token saved. Gmail and Sheets are connected."
    except Exception as e:
        return False, str(e)


def token_json_for_env() -> str | None:
    """Return current token as JSON string for copying to GMAIL_TOKEN_JSON, or None."""
    if not _TOKEN_FILE.exists():
        return None
    return _TOKEN_FILE.read_text(encoding="utf-8")
