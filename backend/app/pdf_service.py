"""
PDF extraction and redaction using PyMuPDF (fitz).

- extract_blocks(): Parse a PDF into a list of TextBlock objects.
- redact_blocks():  Permanently redact specified blocks from a PDF.
"""

import logging

import pymupdf  # PyMuPDF

from app.models import TextBlock

logger = logging.getLogger(__name__)


def extract_blocks(pdf_bytes: bytes) -> tuple[list[TextBlock], int]:
    """
    Extract text blocks from a PDF.

    Each block gets a sequential block_id, its page number,
    bounding box coordinates, and concatenated text content.

    Returns:
        (blocks, page_count)
    """

    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    blocks: list[TextBlock] = []
    block_id = 0

    for page_num in range(len(doc)):
        page = doc[page_num]
        # get_text("dict") returns structured data with blocks -> lines -> spans
        page_dict = page.get_text("dict")

        for block in page_dict.get("blocks", []):
            # Skip image blocks (type 1); keep text blocks (type 0)
            if block.get("type") != 0:
                continue

            # Concatenate all span text within the block
            text_parts: list[str] = []
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text_parts.append(span.get("text", ""))

            text = " ".join(text_parts).strip()

            # Skip empty blocks
            if not text:
                continue

            bbox = block["bbox"]  # (x0, y0, x1, y1)

            blocks.append(
                TextBlock(
                    block_id=block_id,
                    page_number=page_num + 1,  # 1-indexed for readability
                    bbox=list(bbox),
                    text=text,
                )
            )
            block_id += 1

    page_count = len(doc)
    doc.close()

    logger.info("Extracted %d text blocks from %d pages", len(blocks), page_count)
    return blocks, page_count


def redact_blocks(pdf_bytes: bytes, blocks_to_redact: list[TextBlock]) -> bytes:
    """
    Permanently redact the given blocks from the PDF.

    Uses PyMuPDF redaction annotations followed by apply_redactions()
    to ensure the underlying text is truly removed (not just hidden).

    Returns:
        The redacted PDF as bytes.
    """

    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")

    # Group blocks by page for efficient processing
    blocks_by_page: dict[int, list[TextBlock]] = {}
    for block in blocks_to_redact:
        page_idx = block.page_number - 1  # Convert back to 0-indexed
        blocks_by_page.setdefault(page_idx, []).append(block)

    for page_idx, page_blocks in blocks_by_page.items():
        page = doc[page_idx]

        for block in page_blocks:
            rect = pymupdf.Rect(block.bbox)
            # Add a redaction annotation — black fill by default
            page.add_redact_annot(rect)

        # Apply all redactions on this page — permanently removes content
        page.apply_redactions()

    redacted_bytes = doc.tobytes()
    doc.close()

    logger.info(
        "Redacted %d blocks across %d pages",
        len(blocks_to_redact),
        len(blocks_by_page),
    )
    return redacted_bytes
