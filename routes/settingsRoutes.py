from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from service.settingsService import get_reply_prompts, update_reply_prompt, update_reply_prompts

router = APIRouter(prefix="/settings", tags=["Settings"])

class PromptUpdate(BaseModel):
    key: str
    value: str

class ReplyPromptsUpdate(BaseModel):
    quick: str | None = None
    follow_up: str | None = None
    recap: str | None = None


@router.get("/reply-prompts")
def read_reply_prompts():
    return get_reply_prompts()


@router.put("/reply-prompts")
def write_reply_prompts(payload: ReplyPromptsUpdate):
    updated = update_reply_prompts(payload.model_dump(exclude_unset=True))
    return updated


# Backwards-compatible endpoints (older frontend builds)
@router.get("/prompts")
def get_prompts():
    return get_reply_prompts()

@router.post("/prompts")
def update_prompt(data: PromptUpdate):
    if not data.key:
        raise HTTPException(status_code=400, detail="Key is required")
    update_reply_prompt(data.key, data.value)
    return {"status": "updated", "key": data.key}
