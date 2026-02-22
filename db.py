"""
DuckDB connection and schema for Gradient Backend.
Database file is created in the current working directory (e.g. /app in Docker).
"""
import json
import os
from pathlib import Path

import duckdb

_BASE = Path(__file__).resolve().parent
_DB_PATH = os.getenv("DUCKDB_PATH", str(_BASE / "app.duckdb"))

conn = duckdb.connect(_DB_PATH)


def init_db() -> None:
    """Create tables if they do not exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL,
            email TEXT NOT NULL,
            password TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS processed_emails (
            gmail_id TEXT PRIMARY KEY
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cached_replies (
            email_key TEXT NOT NULL,
            subject_key TEXT NOT NULL,
            received_at_key TEXT NOT NULL,
            replies TEXT NOT NULL,
            PRIMARY KEY (email_key, subject_key, received_at_key)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS gmail_messages (
            gmail_id TEXT PRIMARY KEY,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            synced_at TIMESTAMP,
            analyzed_at TIMESTAMP,
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
            preprocessed_at TIMESTAMP
        )
    """)
    conn.commit()


def get_cached_replies(email_key: str, subject_key: str, received_at_key: str) -> list | None:
    """Return cached reply list for this email/subject/received_at, or None if not found."""
    row = conn.execute(
        "SELECT replies FROM cached_replies WHERE email_key = ? AND subject_key = ? AND received_at_key = ?",
        [email_key, subject_key, received_at_key],
    ).fetchone()
    if row is None:
        return None
    try:
        return json.loads(row[0])
    except (json.JSONDecodeError, TypeError):
        return None


def save_cached_replies(email_key: str, subject_key: str, received_at_key: str, replies: list) -> None:
    """Store reply list in cache."""
    conn.execute(
        """
        INSERT INTO cached_replies (email_key, subject_key, received_at_key, replies)
        VALUES (?, ?, ?, ?)
        ON CONFLICT (email_key, subject_key, received_at_key) DO UPDATE SET replies = excluded.replies
        """,
        [email_key, subject_key, received_at_key, json.dumps(replies, ensure_ascii=False)],
    )
    conn.commit()
