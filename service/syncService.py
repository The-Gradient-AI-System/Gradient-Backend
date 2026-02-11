from service.gmailService import (
    fetch_new_gmail_data,
    get_unsynced_message_rows,
    mark_messages_synced,
)
from service.sheetService import append_to_sheet


def sync_gmail_to_sheets(limit: int | None = None) -> int:
    """Fetch new Gmail messages, stage them in DuckDB, then sync unsynced rows to Sheets."""
    fetch_new_gmail_data()

    staged_rows = get_unsynced_message_rows(limit)
    if not staged_rows:
        return 0

    row_values = [values for _, values in staged_rows]
    append_to_sheet(row_values)

    gmail_ids = [gmail_id for gmail_id, _ in staged_rows]
    mark_messages_synced(gmail_ids)

    return len(row_values)
