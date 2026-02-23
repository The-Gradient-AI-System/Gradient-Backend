from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from pydantic import BaseModel, EmailStr, Field

from db import get_cached_replies, save_cached_replies
from service.syncService import sync_gmail_to_sheets
from service.sheetService import build_leads_payload, update_lead_status
from service.aiService import analyze_email, generate_email_replies_six
from service.settingsService import get_reply_prompts
from service import gmail_oauth

router = APIRouter(prefix="/gmail", tags=["Gmail"])


@router.get("/auth")
def gmail_auth():
    """Redirect to Google sign-in. After login, user returns to /gmail/oauth2callback."""
    auth_url, err = gmail_oauth.get_authorization_url()
    if err:
        raise HTTPException(status_code=503, detail=err)
    return RedirectResponse(url=auth_url, status_code=302)


@router.get("/oauth2callback")
def gmail_oauth2callback(code: str | None = None, state: str | None = None, error: str | None = None):
    """Google redirects here after login. Exchange code for token and save token.json."""
    if error:
        return HTMLResponse(
            content=f"<h1>Authorization failed</h1><p>{error}</p><p><a href='/gmail/auth'>Try again</a></p>",
            status_code=400,
        )
    if not code or not state:
        return HTMLResponse(
            content="<h1>Missing code</h1><p>Go to <a href='/gmail/auth'>/gmail/auth</a> to start.</p>",
            status_code=400,
        )
    ok, msg = gmail_oauth.exchange_code_and_save_token(code=code, state=state)
    if not ok:
        return HTMLResponse(
            content=f"<h1>Token error</h1><p>{msg}</p><p><a href='/gmail/auth'>Try again</a></p>",
            status_code=400,
        )
    token_for_env = gmail_oauth.token_json_for_env()
    body = (
        "<h1>Gmail connected</h1><p>Token saved. Auto-sync and /gmail/leads will use it.</p>"
        "<p>On Render: copy the token and set Environment variable <strong>GMAIL_TOKEN_JSON</strong> so it persists after restarts.</p>"
    )
    if token_for_env:
        esc = token_for_env.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        body += f'<script type="application/json" id="token-json">{esc}</script>'
        body += '<button onclick="navigator.clipboard.writeText(document.getElementById(\'token-json\').textContent); this.textContent=\'Copied\'">Copy token</button>'
        body += '<pre style="white-space:pre-wrap;width:100%;max-width:600px;font-size:11px;overflow:auto">' + esc + "</pre>"
    body += '<p><a href="/gmail/auth">Re-authorize</a></p>'
    return HTMLResponse(content=body)


@router.post("/sync")
def manual_sync():
    count = sync_gmail_to_sheets()
    return {"saved": count}


def _empty_leads_payload():
    from datetime import datetime
    now = datetime.utcnow()
    return {
        "leads": [],
        "stats": {"active": 0, "completed": 0, "percentage": 0, "qualified": 0, "waiting": 0},
        "line": [],
        "quarter": [],
        "month": [{"name": "Цей тижд.", "pv": 0, "uv": 0}, {"name": "Минулий", "pv": 0, "uv": 0}, {"name": "2 тиж. тому", "pv": 0, "uv": 0}, {"name": "3+ тиж.", "pv": 0, "uv": 0}],
        "pie": [{"value": 0}, {"value": 100}],
        "generated_at": now.isoformat(),
    }


@router.get("/leads")
def get_leads(limit: int | None = Query(default=120, ge=1, le=500)):
    try:
        return build_leads_payload(limit)
    except FileNotFoundError:
        return _empty_leads_payload()
    except Exception:
        return _empty_leads_payload()


class LeadInsightRequest(BaseModel):
    sender: EmailStr
    subject: str | None = ""
    body: str | None = ""


@router.post("/lead-insights")
def generate_lead_insights(payload: LeadInsightRequest):
    if not payload.body and not payload.subject:
        raise HTTPException(status_code=400, detail="Потрібно передати тему або текст листа")

    result = analyze_email(
        subject=payload.subject or "",
        body=payload.body or "",
        sender=payload.sender,
    )

    return result


class ReplyGenerationRequest(BaseModel):
    sender: EmailStr
    subject: str | None = ""
    body: str | None = ""
    lead: dict | None = None
    placeholders: dict | None = None
    prompt_overrides: dict | None = None
    tone: str | None = None
    email_style: str | None = None


@router.post("/generate-replies")
def generate_replies(payload: ReplyGenerationRequest):
    lead_data = payload.lead or {}
    email_context = {
        "sender": payload.sender,
        "subject": payload.subject or "",
        "body": payload.body or "",
    }
    email_key = (lead_data.get("email") or payload.sender or "").strip()
    subject_key = (lead_data.get("subject") or payload.subject or "").strip()
    received_at_key = (lead_data.get("received_at") or "").strip()

    if email_key and subject_key and received_at_key:
        cached = get_cached_replies(email_key, subject_key, received_at_key)
        if cached is not None:
            return {
                "prompts": get_reply_prompts(),
                "replies": cached,
                "cached": True,
            }
    tone = payload.tone or lead_data.get("tone")

    replies = generate_email_replies_six(
        lead=lead_data,
        email=email_context,
        placeholders=payload.placeholders,
        prompt_overrides=payload.prompt_overrides,
        tone=tone,
    )
    if email_key and subject_key and received_at_key:
        save_cached_replies(email_key, subject_key, received_at_key, replies)

    return {
        "prompts": get_reply_prompts(),
        "replies": replies,
        "cached": False,
    }


class LeadStatusUpdateRequest(BaseModel):
    row_number: int = Field(gt=0)
    status: str


@router.post("/lead-status")
def set_lead_status(payload: LeadStatusUpdateRequest):
    try:
        update_lead_status(payload.row_number, payload.status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"row_number": payload.row_number, "status": payload.status}
