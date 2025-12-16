from fastapi import APIRouter
from service.syncService import sync_gmail_to_sheets

router = APIRouter(prefix="/gmail", tags=["Gmail"])

@router.post("/sync")
def manual_sync():
    count = sync_gmail_to_sheets()
    return {"saved": count}
