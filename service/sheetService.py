import os
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from dotenv import load_dotenv

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

def append_to_sheet(rows: list[list[str]]):
    if not rows:
        return

    creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    service = build("sheets", "v4", credentials=creds)

    body = {"values": rows}

    service.spreadsheets().values().append(
        spreadsheetId=os.getenv("SPREADSHEET_ID"),
        range="A:B",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body=body
    ).execute()
