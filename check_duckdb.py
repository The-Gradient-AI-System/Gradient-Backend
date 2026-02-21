#!/usr/bin/env python3
"""
Перегляд даних DuckDB (НЕ відкривайте database.duckdb у редакторі — це бінарний файл).
Переглядати дані: запустіть цей скрипт.

  python check_duckdb.py          — короткий підсумок
  python check_duckdb.py view     — таблиця листів (останні 20)
  python check_duckdb.py tables  — список таблиць і кількість записів
"""
import sys
from db import conn, DB_PATH


def print_table(rows, headers, max_col=40):
    """Виводить таблицю в консоль з обрізанням довгих значень."""
    if not rows:
        print("  (порожньо)")
        return
    cols = len(headers)
    widths = [min(max(len(str(h)), 4), max_col) for h in headers]
    for row in rows:
        for i, v in enumerate(row):
            if i < len(widths):
                s = str(v)[:max_col] if v else ""
                widths[i] = min(max(widths[i], len(s) + 1), max_col)
    fmt = "  ".join(f"{{:<{w}}}" for w in widths[:cols])
    print(fmt.format(*headers))
    print("-" * (sum(widths[:cols]) + 2 * (cols - 1)))
    for row in rows:
        cells = [str(v)[:max_col] + ("..." if v and len(str(v)) > max_col else "") for v in row]
        print(fmt.format(*(cells[:cols])))


def cmd_summary():
    print(f"DuckDB файл: {DB_PATH}")
    print(f"Існує: {DB_PATH.exists()}\n")

    count = conn.execute("SELECT COUNT(*) FROM gmail_messages").fetchone()[0]
    processed = conn.execute("SELECT COUNT(*) FROM processed_emails").fetchone()[0]
    print(f"Таблиця gmail_messages: {count} записів")
    print(f"Таблиця processed_emails: {processed} записів")

    if count > 0:
        print("\nОстанні 5 листів:")
        rows = conn.execute("""
            SELECT gmail_id, email, subject, received_at, synced_at
            FROM gmail_messages
            ORDER BY created_at DESC
            LIMIT 5
        """).fetchall()
        for r in rows:
            gid, email, subj, recv, synced = r
            subj_short = (subj or "")[:50] + ("..." if len(subj or "") > 50 else "")
            print(f"  {gid[:12]}... | {email} | {subj_short} | {recv} | synced={synced is not None}")
    else:
        print("\nУ gmail_messages поки немає записів.")


def cmd_view():
    print("Таблиця gmail_messages (останні 20 записів):\n")
    rows = conn.execute("""
        SELECT gmail_id, email, subject, received_at,
               CASE WHEN synced_at IS NOT NULL THEN 'так' ELSE 'ні' END AS synced
        FROM gmail_messages
        ORDER BY created_at DESC
        LIMIT 20
    """).fetchall()
    headers = ["gmail_id", "email", "subject", "received_at", "synced"]
    print_table(rows, headers, max_col=50)


def cmd_tables():
    print("Таблиці в базі:\n")
    tables = conn.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'").fetchall()
    for (name,) in tables:
        n = conn.execute(f"SELECT COUNT(*) FROM \"{name}\"").fetchone()[0]
        print(f"  {name}: {n} записів")


def main():
    if len(sys.argv) > 1 and sys.argv[1].strip().lower() == "view":
        cmd_view()
    elif len(sys.argv) > 1 and sys.argv[1].strip().lower() == "tables":
        cmd_tables()
    else:
        cmd_summary()


if __name__ == "__main__":
    main()
