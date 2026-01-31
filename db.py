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

init_db()
