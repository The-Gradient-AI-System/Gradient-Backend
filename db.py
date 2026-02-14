import duckdb
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "db" / "database.duckdb"

DB_PATH.parent.mkdir(parents=True, exist_ok=True)

conn = duckdb.connect(DB_PATH)

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
        synced_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
            ('reply_prompt_recap', ?)
        ) AS defaults(key, value)
        WHERE NOT EXISTS (
            SELECT 1 FROM app_settings WHERE app_settings.key = defaults.key
        )
        """,
        [
            "Act as a Business Development Manager. Draft a concise follow-up email after an intro call. Use only factual details provided. Keep within 140 words and write in English. The structure must cover: greeting with [NAME]; gratitude referencing [TOPIC DISCUSSED]; phrase 'As promised, I'm sharing [LINK_TO_MATERIAL]'; next steps mentioning [NEXT_CONTACT_DATE]; professional signature placeholder [YOUR_NAME].",
            "Act as a Sales Expert. Prepare a recap & proposal email after a qualification call. Use only supplied information. Keep within 140 words and write in English. The structure must cover: greeting with [CLIENT_NAME]; paragraph recognising pains [CLIENT_PAIN_POINTS]; section describing our solution [SOLUTION_OVERVIEW]; bullet list for three proofs each with [PROJECT_NAME] and [RESULT]; closing call-to-action suggesting [NEXT_STEP]."
        ],
    )

init_db()
