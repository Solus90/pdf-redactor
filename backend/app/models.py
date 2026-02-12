"""
Pydantic models for request/response validation.
"""

from pydantic import BaseModel


class TextBlock(BaseModel):
    """A single text block extracted from a PDF page."""
    block_id: int
    page_number: int
    bbox: list[float]  # [x0, y0, x1, y1]
    text: str


class UploadResponse(BaseModel):
    """Returned after a successful PDF upload and extraction."""
    document_id: str
    blocks: list[TextBlock]
    page_count: int


class ClassifyRequest(BaseModel):
    """Request body for the classification endpoint."""
    document_id: str


class ClassifyResponse(BaseModel):
    """AI classification result mapping block IDs to shows."""
    shows: list[str]
    assignments: dict[str, list[int]]  # show_name | "GLOBAL" | "UNCLASSIFIED" -> [block_ids]


class RedactRequest(BaseModel):
    """Request body for the redaction endpoint."""
    document_id: str
    selected_show: str


# ---------------------------------------------------------------------------
# Data extraction models (for Google Sheets export)
# ---------------------------------------------------------------------------


class ShowData(BaseModel):
    """Structured data extracted from a contract for a single show."""
    sponsor_name: str
    show_name: str
    contract_amount: str
    contract_terms: str
    air_dates: str
    cost: str
    billing_cycle: str
    requires_pixel_setup: str  # "Yes" / "No" / "Unknown"
    requires_drafts: str       # "Yes" / "No" / "Unknown"
    ad_frequency: str


class ExtractRequest(BaseModel):
    """Request body for the data extraction endpoint."""
    document_id: str


class ExtractResponse(BaseModel):
    """Result of extracting structured data and pushing to Google Sheets."""
    shows: list[ShowData]
    rows_added: int
    sheet_url: str
