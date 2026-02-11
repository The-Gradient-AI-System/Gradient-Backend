from typing import Dict

from db import conn

ReplyPrompts = Dict[str, str]

FOLLOW_UP_KEY = "reply_prompt_follow_up"
RECAP_KEY = "reply_prompt_recap"


def get_setting(key: str) -> str | None:
    row = conn.execute("SELECT value FROM app_settings WHERE key = ?", [key]).fetchone()
    return row[0] if row else None


def set_setting(key: str, value: str) -> None:
    conn.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)", [key, value])


def get_reply_prompts() -> ReplyPrompts:
    follow_up = get_setting(FOLLOW_UP_KEY) or ""
    recap = get_setting(RECAP_KEY) or ""
    return {
        "follow_up": follow_up,
        "recap": recap,
    }


def update_reply_prompts(follow_up: str, recap: str) -> ReplyPrompts:
    set_setting(FOLLOW_UP_KEY, follow_up)
    set_setting(RECAP_KEY, recap)
    return get_reply_prompts()
