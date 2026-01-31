from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, EmailStr, Field

from service.syncService import sync_gmail_to_sheets
from service.sheetService import build_leads_payload, update_lead_status
from service.aiService import analyze_email

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
