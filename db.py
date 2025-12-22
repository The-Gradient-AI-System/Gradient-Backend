import duckdb
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "db" / "database.duckdb"

conn = duckdb.connect(DB_PATH)

def init_db():
    conn.execute("CREATE SEQUENCE IF NOT EXISTS user_id_seq START WITH 1;")

    conn.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY DEFAULT nextval('user_id_seq'),
        username TEXT UNIQUE NOT NULL,
        email TEXT NOT NULL,
        password TEXT NOT NULL,
        phrase_hash TEXT,
        phrase_expires_at TIMESTAMP,
        phrase_revoked BOOLEAN DEFAULT FALSE
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS processed_emails (
        gmail_id TEXT PRIMARY KEY,
        processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

init_db()
