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
