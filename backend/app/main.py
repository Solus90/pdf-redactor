"""
FastAPI application — PDF Redactor for multi-show sponsorship contracts.

Endpoints:
  POST /api/upload    — Upload a PDF; extract text blocks.
  POST /api/classify  — Classify blocks by show via Claude AI.
  POST /api/redact    — Generate a redacted PDF for a selected show.
  POST /api/extract   — Extract structured data and push to Google Sheets.
"""

import os
import uuid
import logging
from io import BytesIO

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv

from app.models import (
    TextBlock,
    UploadResponse,
    ClassifyRequest,
    ClassifyResponse,
    RedactRequest,
    ExtractRequest,
    ExtractResponse,
)
import gspread.exceptions as gspread_exc

from app.pdf_service import extract_blocks, redact_blocks
from app.ai_service import classify_blocks, extract_contract_data
from app.sheets_service import append_rows

# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="PDF Redactor", version="0.1.0")

# Allow frontend origins (local dev + production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "https://pdf-redactor-frontend.onrender.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# In-memory document store  (MVP — no database)
# ---------------------------------------------------------------------------

# { document_id: { "pdf_bytes": bytes, "blocks": [TextBlock], "classification": ClassifyResponse | None } }
documents: dict[str, dict] = {}

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/api/sheets-check")
async def check_sheets_connection():
    """
    Test Google Sheets connection. Returns success or the actual error for debugging.
    """
    try:
        from app.sheets_service import _get_client

        sheet_id = os.environ.get("GOOGLE_SHEET_ID")
        if not sheet_id or sheet_id.strip() in ("", "your-spreadsheet-id-here"):
            return {"ok": False, "error": "GOOGLE_SHEET_ID not set in .env"}

        client = _get_client()
        spreadsheet = client.open_by_key(sheet_id)
        spreadsheet.url  # trigger access
        return {"ok": True, "sheet_title": spreadsheet.title}
    except Exception as exc:
        msg = str(exc) or (f"{type(exc).__name__}: " + repr(exc.args))
        logger.exception("Sheets check failed: %s", exc)
        return {"ok": False, "error": msg, "type": type(exc).__name__}


@app.post("/api/upload", response_model=UploadResponse)
async def upload_pdf(file: UploadFile = File(...)):
    """Accept a PDF upload, extract text blocks with bounding boxes."""

    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(status_code=400, detail="File must be a PDF.")

    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # Extract text blocks from the PDF
    blocks, page_count = extract_blocks(pdf_bytes)
    if not blocks:
        raise HTTPException(
            status_code=422,
            detail="No text blocks found in the PDF. Is it a scanned document?",
        )

    document_id = str(uuid.uuid4())
    documents[document_id] = {
        "pdf_bytes": pdf_bytes,
        "blocks": blocks,
        "classification": None,
    }

    logger.info(
        "Uploaded document %s — %d blocks across %d pages",
        document_id,
        len(blocks),
        page_count,
    )

    return UploadResponse(
        document_id=document_id,
        blocks=blocks,
        page_count=page_count,
    )


@app.post("/api/classify", response_model=ClassifyResponse)
async def classify_document(req: ClassifyRequest):
    """Send extracted blocks to Claude for show-level classification."""

    doc = documents.get(req.document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(
            status_code=503,
            detail="Anthropic API key not configured. Add ANTHROPIC_API_KEY to backend/.env",
        )

    try:
        classification = await classify_blocks(doc["blocks"])
    except Exception as exc:
        logger.exception("Classification failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=f"Claude classification failed: {exc!s}. Check your API key and quota.",
        ) from exc
    doc["classification"] = classification

    logger.info(
        "Classified document %s — shows: %s",
        req.document_id,
        classification.shows,
    )

    return classification


@app.post("/api/redact")
async def redact_document(req: RedactRequest):
    """Generate a permanently redacted PDF for the selected show."""

    doc = documents.get(req.document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")

    classification = doc.get("classification")
    if classification is None:
        raise HTTPException(
            status_code=400,
            detail="Document has not been classified yet. Call /api/classify first.",
        )

    if req.selected_show not in classification.shows:
        raise HTTPException(
            status_code=400,
            detail=f"Show '{req.selected_show}' not found. Available: {classification.shows}",
        )

    # Determine which block IDs to KEEP (selected show + GLOBAL)
    # GLOBAL_REDACT blocks (aggregate totals) are intentionally NOT kept
    keep_ids: set[int] = set()
    keep_ids.update(classification.assignments.get(req.selected_show, []))
    keep_ids.update(classification.assignments.get("GLOBAL", []))

    # Everything else gets redacted (other shows, UNCLASSIFIED, GLOBAL_REDACT)
    blocks_to_redact = [b for b in doc["blocks"] if b.block_id not in keep_ids]

    logger.info(
        "Redacting document %s for show '%s' — keeping %d blocks, redacting %d blocks",
        req.document_id,
        req.selected_show,
        len(keep_ids),
        len(blocks_to_redact),
    )

    redacted_pdf = redact_blocks(doc["pdf_bytes"], blocks_to_redact)

    return StreamingResponse(
        BytesIO(redacted_pdf),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="redacted_{req.selected_show}.pdf"'
        },
    )


@app.post("/api/extract", response_model=ExtractResponse)
async def extract_to_sheets(req: ExtractRequest):
    """Extract structured contract data and push to Google Sheets."""

    doc = documents.get(req.document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")

    classification = doc.get("classification")
    if classification is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise HTTPException(
                status_code=503,
                detail="Anthropic API key not configured. Add ANTHROPIC_API_KEY to backend/.env",
            )
        try:
            classification = await classify_blocks(doc["blocks"])
            doc["classification"] = classification
        except Exception as exc:
            logger.exception("Classification failed during extract: %s", exc)
            raise HTTPException(
                status_code=503,
                detail=f"Classification failed: {exc!s}. Check your API key and quota.",
            ) from exc

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(
            status_code=503,
            detail="Anthropic API key not configured. Add ANTHROPIC_API_KEY to backend/.env",
        )

    # Step 1: Extract structured data via AI
    try:
        show_data = await extract_contract_data(doc["blocks"], classification)
    except Exception as exc:
        logger.exception("Data extraction failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=f"Data extraction failed: {exc!s}",
        ) from exc

    if not show_data:
        raise HTTPException(
            status_code=422,
            detail="AI could not extract any show data from the contract.",
        )

    # Step 2: Push to Google Sheets
    try:
        sheet_url = append_rows(show_data)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except PermissionError:
        raise HTTPException(
            status_code=503,
            detail="Cannot read credentials.json. Check file permissions and that GOOGLE_CREDENTIALS_PATH points to the correct file.",
        ) from None
    except gspread_exc.APIError as exc:
        msg = str(exc)
        err = getattr(exc, "error", None)
        if isinstance(err, dict):
            msg = err.get("message", msg) or msg
        if not msg:
            msg = "Permission denied or invalid sheet ID. Share the sheet with your service account email (in credentials.json) as Editor."
        raise HTTPException(
            status_code=503,
            detail=f"Google Sheets error: {msg}",
        ) from exc
    except gspread_exc.SpreadsheetNotFound:
        raise HTTPException(
            status_code=503,
            detail="Spreadsheet not found. Check GOOGLE_SHEET_ID and ensure the sheet is shared with your service account (Editor access).",
        ) from None
    except Exception as exc:
        logger.exception("Google Sheets export failed: %s", exc)
        # Extract useful message from various exception types
        msg = str(exc)
        if not msg and getattr(exc, "args", None):
            msg = " ".join(str(a) for a in exc.args if a)
        if not msg and exc.__cause__:
            msg = str(exc.__cause__)
        if not msg:
            msg = f"{type(exc).__name__} (no message)"
        raise HTTPException(
            status_code=503,
            detail=f"Google Sheets export failed: {msg}. Check credentials.json, GOOGLE_SHEET_ID, and that the sheet is shared with the service account.",
        ) from exc

    logger.info(
        "Exported %d rows to Google Sheets for document %s",
        len(show_data),
        req.document_id,
    )

    return ExtractResponse(
        shows=show_data,
        rows_added=len(show_data),
        sheet_url=sheet_url,
    )
