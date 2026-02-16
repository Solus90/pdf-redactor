"""
Google Sheets integration using gspread.

Pushes extracted contract data to a fixed Google Sheet
configured via environment variables.
"""

import json
import os
import logging

import gspread

from app.models import ShowData

logger = logging.getLogger(__name__)

# Column headers matching the ShowData fields
HEADERS = [
    "Podcast Booked",
    "Agency",
    "Advertiser",
    "Type",
    "Insertion Date Per IO",
    "Draft Required (Y/N)",
    "Impressions",
    "Amount",
    "Payment Terms",
    "Requires Pixel Tracker(Y/N)",
    "Notes",
]


def _get_client() -> gspread.Client:
    """Create an authorized gspread client from the service account credentials."""

    # Option 1: Credentials from env var (avoids file permission issues)
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if creds_json:
        try:
            creds_dict = json.loads(creds_json)
            return gspread.service_account_from_dict(creds_dict)
        except json.JSONDecodeError as e:
            raise ValueError(
                "GOOGLE_CREDENTIALS_JSON is invalid JSON. Paste the full contents of credentials.json."
            ) from e

    # Option 2: Credentials from file
    creds_path = os.environ.get("GOOGLE_CREDENTIALS_PATH", "./credentials.json")
    if not os.path.isabs(creds_path):
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        creds_path = os.path.normpath(os.path.join(backend_dir, creds_path))
    creds_path = os.path.abspath(creds_path)

    if not os.path.exists(creds_path):
        raise FileNotFoundError(
            f"Google credentials file not found at '{creds_path}'. "
            "Set GOOGLE_CREDENTIALS_PATH in .env, or use GOOGLE_CREDENTIALS_JSON with the full JSON."
        )

    return gspread.service_account(filename=creds_path)


def _yn_to_bool(value: str) -> bool:
    """Convert Y/N string to boolean for Google Sheets checkboxes."""
    return value.strip().upper() in ("Y", "YES", "TRUE")


def _show_data_to_row(show: ShowData) -> list:
    """Convert a ShowData object to a flat list of cell values."""
    return [
        show.podcast_booked,
        show.agency,
        show.advertiser,
        show.type,
        show.insertion_date_per_io,
        _yn_to_bool(show.draft_required_yn),
        show.impressions,
        show.amount,
        show.payment_terms,
        _yn_to_bool(show.requires_pixel_tracker_yn),
        show.notes,
    ]


def append_rows(rows: list[ShowData]) -> str:
    """
    Append extracted show data to the configured Google Sheet.

    - Opens the spreadsheet by ID from GOOGLE_SHEET_ID env var.
    - Uses the first worksheet.
    - Writes a header row if the sheet is empty.
    - Appends one row per ShowData object.

    Returns:
        The URL of the spreadsheet.
    """

    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    if not sheet_id or sheet_id.strip() in ("", "your-spreadsheet-id-here"):
        raise ValueError(
            "GOOGLE_SHEET_ID not configured. Add your Google Sheet ID to backend/.env (the long ID from the sheet URL)."
        )

    client = _get_client()
    spreadsheet = client.open_by_key(sheet_id)
    worksheet = spreadsheet.sheet1

    # Write headers if the sheet is empty
    existing = worksheet.get_all_values()
    if not existing:
        worksheet.append_row(HEADERS, value_input_option="USER_ENTERED", table_range="A1")
        logger.info("Wrote header row to Google Sheet")

    # Append each show as a row
    for show in rows:
        row = _show_data_to_row(show)
        worksheet.append_row(row, value_input_option="USER_ENTERED", table_range="A1")

    logger.info("Appended %d rows to Google Sheet '%s'", len(rows), sheet_id)
    return spreadsheet.url
