from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, EmailStr, Field

from db import get_cached_replies, save_cached_replies
from service.syncService import sync_gmail_to_sheets
from service.sheetService import build_leads_payload, update_lead_status
from service.aiService import analyze_email, generate_email_replies_six
from service.settingsService import get_reply_prompts

router = APIRouter(prefix="/gmail", tags=["Gmail"])

@router.post("/sync")
def manual_sync():
    count = sync_gmail_to_sheets()
    return {"saved": count}


@router.get("/leads")
def get_leads(limit: int | None = Query(default=120, ge=1, le=500)):
    payload = build_leads_payload(limit)
    return payload


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
