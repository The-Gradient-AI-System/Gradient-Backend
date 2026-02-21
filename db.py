import duckdb
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "db" / "database.duckdb"

DB_PATH.parent.mkdir(parents=True, exist_ok=True)

conn = duckdb.connect(DB_PATH)


def _migrate_gmail_messages_stage1_columns():
    """Додає колонки Етапу 1 до існуючої таблиці gmail_messages (якщо їх ще немає)."""
    new_columns = [
        ("is_lead", "BOOLEAN"),
        ("priority", "TEXT"),
        ("status_label", "TEXT"),
        ("tone", "TEXT"),
        ("preprocessed_at", "TIMESTAMP"),
    ]
    for col_name, col_type in new_columns:
        try:
            conn.execute(f"ALTER TABLE gmail_messages ADD COLUMN {col_name} {col_type}")
        except Exception as e:
            if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                pass
            else:
                raise


def _migrate_gmail_messages_analyzed_at():
    """Додає колонку analyzed_at: заповнюється після analyze_email, синхронізація в Sheets тільки тоді."""
    try:
        conn.execute("ALTER TABLE gmail_messages ADD COLUMN analyzed_at TIMESTAMP")
    except Exception as e:
        if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
            pass
        else:
            raise


def init_db():
    conn.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        email TEXT NOT NULL,
        password TEXT NOT NULL
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS processed_emails (
        gmail_id TEXT PRIMARY KEY,
        processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS gmail_messages (
        gmail_id TEXT PRIMARY KEY,
        status TEXT,
        first_name TEXT,
        last_name TEXT,
        full_name TEXT,
        email TEXT,
        subject TEXT,
        received_at TEXT,
        company TEXT,
        body TEXT,
        phone TEXT,
        website TEXT,
        company_name TEXT,
        company_info TEXT,
        person_role TEXT,
        person_links TEXT,
        person_location TEXT,
        person_experience TEXT,
        person_summary TEXT,
        person_insights TEXT,
        company_insights TEXT,
        is_lead BOOLEAN,
        priority TEXT,
        status_label TEXT,
        tone TEXT,
        preprocessed_at TIMESTAMP,
        synced_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    _migrate_gmail_messages_stage1_columns()
    _migrate_gmail_messages_analyzed_at()

    conn.execute("""
    CREATE TABLE IF NOT EXISTS cached_replies (
        email TEXT NOT NULL,
        subject TEXT NOT NULL,
        received_at TEXT NOT NULL,
        quick_official TEXT,
        quick_semi TEXT,
        follow_up_official TEXT,
        follow_up_semi TEXT,
        recap_official TEXT,
        recap_semi TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (email, subject, received_at)
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS app_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """)

    conn.execute(
        """
        INSERT INTO app_settings (key, value)
        SELECT * FROM (VALUES
            ('reply_prompt_follow_up', ?),
            ('reply_prompt_recap', ?),
            ('reply_prompt_quick', ?)
        ) AS defaults(key, value)
        WHERE NOT EXISTS (
            SELECT 1 FROM app_settings WHERE app_settings.key = defaults.key
        )
        """,
        [
            "Act as a Business Development Manager. Draft a concise follow-up email after an intro call. Use only factual details provided. Keep within 140 words and write in English. The structure must cover: greeting with [NAME]; gratitude referencing [TOPIC DISCUSSED]; phrase 'As promised, I'm sharing [LINK_TO_MATERIAL]'; next steps mentioning [NEXT_CONTACT_DATE]; professional signature placeholder [YOUR_NAME].",
            "Act as a Sales Expert. Prepare a recap & proposal email after a qualification call. Use only supplied information. Keep within 140 words and write in English. The structure must cover: greeting with [CLIENT_NAME]; paragraph recognising pains [CLIENT_PAIN_POINTS]; section describing our solution [SOLUTION_OVERVIEW]; bullet list for three proofs each with [PROJECT_NAME] and [RESULT]; closing call-to-action suggesting [NEXT_STEP].",
            "Act as a Sales Assistant. Write a very short, friendly reply (max 60 words). Use only facts provided. Keep it casual and professional. Structure: greeting + brief acknowledgment + next step or closing. Use placeholders like [NAME] and [TOPIC]."
        ],
    )


CACHED_REPLY_KEYS = (
    "quick_official", "quick_semi",
    "follow_up_official", "follow_up_semi",
    "recap_official", "recap_semi",
)


def get_cached_replies(email: str, subject: str, received_at: str) -> dict[str, str] | None:
    """Повертає кешовані 6 відповідей за ключем (email, subject, received_at) або None."""
    row = conn.execute(
        """
        SELECT quick_official, quick_semi, follow_up_official, follow_up_semi, recap_official, recap_semi
        FROM cached_replies
        WHERE email = ? AND subject = ? AND received_at = ?
        """,
        [email, subject, received_at],
    ).fetchone()
    if not row:
        return None
    out = {}
    for i, key in enumerate(CACHED_REPLY_KEYS):
        val = row[i]
        out[key] = val if val is not None else ""
    return out


def save_cached_replies(email: str, subject: str, received_at: str, replies: dict[str, str]) -> None:
    """Зберігає 6 відповідей у кеш (перезаписує при існуючому ключі)."""
    conn.execute(
        """
        INSERT OR REPLACE INTO cached_replies
        (email, subject, received_at, quick_official, quick_semi, follow_up_official, follow_up_semi, recap_official, recap_semi, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        [
            email,
            subject,
            received_at,
            replies.get("quick_official") or "",
            replies.get("quick_semi") or "",
            replies.get("follow_up_official") or "",
            replies.get("follow_up_semi") or "",
            replies.get("recap_official") or "",
            replies.get("recap_semi") or "",
        ],
    )


init_db()
