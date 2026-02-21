from __future__ import annotations

from db import conn

_PROMPT_DB_PREFIX = "reply_prompt_"
_VARIANTS = ("quick", "follow_up", "recap")


def _variant_to_db_key(variant: str) -> str:
    return f"{_PROMPT_DB_PREFIX}{variant}"


def _db_key_to_variant(key: str) -> str | None:
    if not key or not key.startswith(_PROMPT_DB_PREFIX):
        return None
    variant = key[len(_PROMPT_DB_PREFIX) :].strip()
    return variant if variant in _VARIANTS else None


def get_reply_prompts() -> dict[str, str]:
    """Return prompts in the shape expected by frontend/AI: {quick, follow_up, recap}."""
    rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
    prompts: dict[str, str] = {variant: "" for variant in _VARIANTS}
    for db_key, value in rows:
        variant = _db_key_to_variant(str(db_key))
        if not variant:
            continue
        prompts[variant] = value or ""
    return prompts


def update_reply_prompts(prompts: dict[str, str]) -> dict[str, str]:
    """Update multiple prompts at once. Unknown keys are ignored."""
    for variant in _VARIANTS:
        if variant not in prompts:
            continue
        value = prompts.get(variant)
        if not isinstance(value, str):
            continue
        update_reply_prompt(_variant_to_db_key(variant), value)
    return get_reply_prompts()


def update_reply_prompt(key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO app_settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        [key, value],
    )
