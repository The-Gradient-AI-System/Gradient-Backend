import os
import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
CREDENTIALS_DIR = BASE_DIR / "credentials"
TOKEN_FILE = CREDENTIALS_DIR / "token.json"

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _get_sheet_service():
    if not TOKEN_FILE.exists():
        raise FileNotFoundError(
            f"token.json not found at {TOKEN_FILE}. "
            "Run auth_init.py first."
        )

    creds = Credentials.from_authorized_user_file(
        TOKEN_FILE,
        SCOPES
    )

    return build("sheets", "v4", credentials=creds)


def append_to_sheet(rows: list[list[str]]):
    if not rows:
        return

    service = _get_sheet_service()

    body = {"values": rows}

    service.spreadsheets().values().append(
        spreadsheetId=os.getenv("SPREADSHEET_ID"),
        range="A:T",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body=body
    ).execute()


DEFAULT_HEADERS = [
    "status",
    "first_name",
    "last_name",
    "full_name",
    "email",
    "subject",
    "received_at",
    "company",
    "body",
    "phone",
    "website",
    "company_name",
    "company_info",
    "person_role",
    "person_links",
    "person_location",
    "person_experience",
    "person_summary",
    "person_insights",
    "company_insights",
]


MONTH_LABELS = [
    "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
    "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
]

WEEK_LABELS = ["W1", "W2", "W3", "W4"]

DATE_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
    "%d.%m.%Y %H:%M:%S",
    "%d.%m.%Y",
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y",
]


def fetch_sheet_rows(limit: int | None = 120) -> list[dict[str, str]]:
    service = _get_sheet_service()

    result = service.spreadsheets().values().get(
        spreadsheetId=os.getenv("SPREADSHEET_ID"),
        range="A:T"
    ).execute()

    values = result.get("values", [])
    if not values:
        return []

    header_row = values[0]
    normalized = [cell.strip().lower() for cell in header_row]

    treated_as_header = any(col in ("email", "subject", "company") for col in normalized)

    if treated_as_header:
        header = [DEFAULT_HEADERS[i] if i < len(DEFAULT_HEADERS) else f"field_{i}" for i, _ in enumerate(header_row)]
        data_rows = values[1:]
        header_offset = 1
    else:
        header = DEFAULT_HEADERS
        data_rows = values
        header_offset = 0

    data_rows = list(data_rows)
    total_rows = len(data_rows)

    if limit is not None and limit > 0:
        data_rows = data_rows[-limit:]

    trimmed_count = total_rows - len(data_rows)
    start_row_number = 1 + header_offset + trimmed_count

    indexed_rows = list(enumerate(data_rows, start=start_row_number))

    leads = []
    for row_number, row in reversed(indexed_rows):  # newest first
        entry = {}
        for idx, key in enumerate(header):
            if idx < len(DEFAULT_HEADERS):
                key = DEFAULT_HEADERS[idx]
            entry[key] = row[idx] if idx < len(row) else ""

        # Post-process JSON encoded fields
        person_links_raw = entry.get("person_links")
        if person_links_raw:
            try:
                entry["person_links"] = json.loads(person_links_raw)
            except json.JSONDecodeError:
                entry["person_links"] = [item.strip() for item in person_links_raw.split(";") if item.strip()]
        else:
            entry["person_links"] = []

        for complex_key in ("person_insights", "company_insights"):
            raw_value = entry.get(complex_key)
            if raw_value:
                try:
                    entry[complex_key] = json.loads(raw_value)
                except json.JSONDecodeError:
                    entry[complex_key] = []
            else:
                entry[complex_key] = []

        # Normalize optional fields
        entry["status"] = entry.get("status") or "waiting"
        entry["person_summary"] = entry.get("person_summary") or ""
        entry["first_name"] = entry.get("first_name") or ""
        entry["last_name"] = entry.get("last_name") or ""
        entry["sheet_row"] = row_number

        leads.append(entry)

    return leads


ALLOWED_STATUS_VALUES = {"confirmed", "rejected", "snoozed", "waiting", "new"}


def update_lead_status(row_number: int, status: str) -> None:
    if row_number is None or row_number < 1:
        raise ValueError("row_number must be a positive integer")

    normalized_status = (status or "").strip().lower()
    if normalized_status not in ALLOWED_STATUS_VALUES:
        raise ValueError("Unsupported status value")

    service = _get_sheet_service()

    body = {"values": [[normalized_status]]}

    service.spreadsheets().values().update(
        spreadsheetId=os.getenv("SPREADSHEET_ID"),
        range=f"A{row_number}",
        valueInputOption="RAW",
        body=body,
    ).execute()


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None

    stripped = value.strip()
    if not stripped:
        return None

    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(stripped, fmt)
        except ValueError:
            continue

    try:
        normalized = stripped.replace("Z", "+00:00") if stripped.endswith("Z") else stripped
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _generate_month_buckets() -> list[datetime]:
    buckets: list[datetime] = []
    current = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    for _ in range(12):
        buckets.append(current)
        month = current.month - 1
        year = current.year
        if month == 0:
            month = 12
            year -= 1
        current = datetime(year, month, 1)
    return list(reversed(buckets))


def _is_qualified(lead: dict[str, str]) -> bool:
    return bool(lead.get("phone") or lead.get("website") or lead.get("company"))


def build_leads_payload(limit: int | None = 120) -> dict[str, Any]:
    leads = fetch_sheet_rows(limit)
    now = datetime.utcnow()
    active_cutoff = now - timedelta(days=30)

    total = len(leads)
    qualified_total = 0
    waiting_total = 0
    active_total = 0

    month_totals: dict[tuple[int, int], dict[str, int]] = defaultdict(lambda: {"total": 0, "qualified": 0})
    week_totals = [0, 0, 0, 0]
    week_qualified = [0, 0, 0, 0]

    for lead in leads:
        lead_dt = _parse_datetime(lead.get("received_at"))
        qualified = _is_qualified(lead)
        if qualified:
            qualified_total += 1

        if (lead.get("status") or "waiting").lower() == "waiting" and not qualified:
            waiting_total += 1

        if lead_dt:
            if lead_dt >= active_cutoff:
                active_total += 1

            key = (lead_dt.year, lead_dt.month)
            month_totals[key]["total"] += 1
            if qualified:
                month_totals[key]["qualified"] += 1

            diff_days = (now - lead_dt).days
            if diff_days < 0:
                diff_days = 0
            week_index = diff_days // 7
            if week_index < 4:
                slot = 3 - week_index
                week_totals[slot] += 1
                if qualified:
                    week_qualified[slot] += 1

    month_buckets = _generate_month_buckets()
    line_chart = []
    for bucket in month_buckets:
        key = (bucket.year, bucket.month)
        bucket_totals = month_totals.get(key, {"total": 0, "qualified": 0})
        line_chart.append({
            "name": MONTH_LABELS[bucket.month - 1],
            "pv": bucket_totals["total"],
            "uv": bucket_totals["qualified"],
        })

    quarter_chart = line_chart[-3:] if line_chart else []

    month_chart = [
        {"name": label, "pv": week_totals[idx], "uv": week_qualified[idx]}
        for idx, label in enumerate(WEEK_LABELS)
    ]

    percentage = 0
    if total:
        percentage = int(round((qualified_total / total) * 100))

    pie_chart = [
        {"value": percentage},
        {"value": max(0, 100 - percentage)},
    ] if total else [{"value": 0}, {"value": 100}]

    stats = {
        "active": active_total,
        "completed": total,
        "percentage": percentage,
        "qualified": qualified_total,
        "waiting": waiting_total,
    }

    return {
        "leads": leads,
        "stats": stats,
        "line": line_chart,
        "quarter": quarter_chart,
        "month": month_chart,
        "pie": pie_chart,
        "generated_at": now.isoformat(),
    }
