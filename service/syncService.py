from service.gmailService import fetch_new_gmail_data
from service.sheetService import append_to_sheet

def sync_gmail_to_sheets():
    rows = fetch_new_gmail_data()
    append_to_sheet(rows)
    return len(rows)
