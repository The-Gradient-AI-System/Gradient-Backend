from fastapi import APIRouter
from pydantic import BaseModel, Field

from service.settingsService import get_reply_prompts, update_reply_prompts

router = APIRouter(prefix="/settings", tags=["Settings"])


class ReplyPromptsPayload(BaseModel):
    follow_up: str = Field(min_length=1, description="Prompt used for follow-up replies")
    recap: str = Field(min_length=1, description="Prompt used for recap replies")


@router.get("/reply-prompts")
def read_reply_prompts() -> ReplyPromptsPayload:
    prompts = get_reply_prompts()
    return ReplyPromptsPayload(**prompts)


@router.put("/reply-prompts")
def write_reply_prompts(payload: ReplyPromptsPayload) -> ReplyPromptsPayload:
    updated = update_reply_prompts(payload.follow_up, payload.recap)
    return ReplyPromptsPayload(**updated)
