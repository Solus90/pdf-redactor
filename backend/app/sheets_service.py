"""
Google Sheets integration using gspread.

Pushes extracted contract data to a fixed Google Sheet
configured via environment variables.
"""

import os
import logging

import gspread

from app.models import ShowData

logger = logging.getLogger(__name__)

# Column headers matching the ShowData fields
HEADERS = [
    "Sponsor Name",
    "Show Name",
    "Contract Amount",
    "Contract Terms",
    "Air Dates / Flight Dates",
    "Cost",
    "Billing Cycle",
    "Requires Pixel Setup",
    "Requires Drafts",
    "Ad Frequency",
]


def _get_client() -> gspread.Client:
    """Create an authorized gspread client from the service account credentials."""

    creds_path = os.environ.get("GOOGLE_CREDENTIALS_PATH", "./credentials.json")
    if not os.path.exists(creds_path):
        raise FileNotFoundError(
            f"Google credentials file not found at '{creds_path}'. "
            "Set GOOGLE_CREDENTIALS_PATH in .env or place credentials.json in the backend/ directory."
        )

    return gspread.service_account(filename=creds_path)


def _show_data_to_row(show: ShowData) -> list[str]:
    """Convert a ShowData object to a flat list of cell values."""
    return [
        show.sponsor_name,
        show.show_name,
        show.contract_amount,
        show.contract_terms,
        show.air_dates,
        show.cost,
        show.billing_cycle,
        show.requires_pixel_setup,
        show.requires_drafts,
        show.ad_frequency,
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
    if not sheet_id:
        raise ValueError(
            "GOOGLE_SHEET_ID not configured. Add it to backend/.env"
        )

    client = _get_client()
    spreadsheet = client.open_by_key(sheet_id)
    worksheet = spreadsheet.sheet1

    # Write headers if the sheet is empty
    existing = worksheet.get_all_values()
    if not existing:
        worksheet.append_row(HEADERS, value_input_option="USER_ENTERED")
        logger.info("Wrote header row to Google Sheet")

    # Append each show as a row
    for show in rows:
        row = _show_data_to_row(show)
        worksheet.append_row(row, value_input_option="USER_ENTERED")

    logger.info("Appended %d rows to Google Sheet '%s'", len(rows), sheet_id)
    return spreadsheet.url
