import duckdb

conn = duckdb.connect("db/database.duckdb")

def init_db():
    conn.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER,
        username TEXT NOT NULL,
        email TEXT NOT NULL,
        password TEXT NOT NULL
    )
    """)

init_db()
