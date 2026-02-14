from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from service.settingsService import get_reply_prompts, update_reply_prompt

router = APIRouter(prefix="/settings", tags=["Settings"])

class PromptUpdate(BaseModel):
    key: str
    value: str

@router.get("/prompts")
def get_prompts():
    return get_reply_prompts()

@router.post("/prompts")
def update_prompt(data: PromptUpdate):
    if not data.key:
        raise HTTPException(status_code=400, detail="Key is required")
    update_reply_prompt(data.key, data.value)
    return {"status": "updated", "key": data.key}
