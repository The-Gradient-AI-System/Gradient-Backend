import asyncio
from pathlib import Path
from service.syncService import sync_gmail_to_sheets

_BASE_DIR = Path(__file__).resolve().parent.parent
_TOKEN_FILE = _BASE_DIR / "credentials" / "token.json"
_token_missing_logged = False


def _is_token_missing_error(exc: Exception) -> bool:
    if isinstance(exc, FileNotFoundError):
        return True
    msg = getattr(exc, "args", ()) and str(exc) or ""
    return "token.json" in msg or "Authorize Gmail" in msg


async def auto_sync_loop():
    global _token_missing_logged
    while True:
        try:
            if not _TOKEN_FILE.exists():
                if not _token_missing_logged:
                    print(
                        "[AUTO SYNC] Gmail token not configured. "
                        "Set GMAIL_TOKEN_JSON in Environment or authorize at GET /gmail/auth"
                    )
                    _token_missing_logged = True
                await asyncio.sleep(60)
                continue
            _token_missing_logged = False
            count = sync_gmail_to_sheets()
            if count:
                print(f"[AUTO SYNC] saved {count} new emails")
        except Exception as e:
            if _is_token_missing_error(e):
                if not _token_missing_logged:
                    print(
                        "[AUTO SYNC] Gmail token missing. "
                        "Set GMAIL_TOKEN_JSON on Render or use GET /gmail/auth to authorize."
                    )
                    _token_missing_logged = True
            else:
                print(f"[AUTO SYNC ERROR] {e}")

        await asyncio.sleep(60)
