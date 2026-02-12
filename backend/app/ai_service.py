"""
AI-powered block classification using OpenAI.

Sends extracted text blocks to the model and receives a JSON mapping
of block IDs to shows (plus GLOBAL and UNCLASSIFIED categories).
"""

import json
import os
import logging

from openai import AsyncOpenAI

from app.models import TextBlock, ClassifyResponse

logger = logging.getLogger(__name__)

# Maximum characters per block sent to the model (saves tokens)
MAX_BLOCK_TEXT_LEN = 500

SYSTEM_PROMPT = """\
You are a document analyst specializing in multi-show sponsorship contracts.

You will receive a list of text blocks extracted from a PDF contract. Each block
has an integer ID and its text content. The contract covers sponsorship terms for
MULTIPLE shows/programs.

Your task:
1. Identify every unique show/program name mentioned in the contract.
2. Classify each block into exactly ONE of the following categories:
   - A specific show name (if the block relates to that show only).
   - "GLOBAL" — if the block applies to ALL shows (e.g., general terms,
     signatures, party names, dates, governing law, universal clauses).
   - "UNCLASSIFIED" — if you cannot confidently determine which show
     the block belongs to.

Rules:
- Every block ID must appear in exactly one category.
- Show names should be normalized (consistent capitalization/spelling).
- Section headers that introduce a show-specific section belong to that show.
- Shared header/footer text, preamble, and signature blocks are GLOBAL.

Respond with valid JSON in this exact structure:
{
  "shows": ["Show Name A", "Show Name B"],
  "assignments": {
    "Show Name A": [1, 3, 5],
    "Show Name B": [2, 4, 6],
    "GLOBAL": [0, 7, 8],
    "UNCLASSIFIED": [9]
  }
}
"""


def _build_user_message(blocks: list[TextBlock]) -> str:
    """Format extracted blocks into a numbered list for the model."""

    lines: list[str] = []
    lines.append(f"The document contains {len(blocks)} text blocks:\n")

    for block in blocks:
        # Truncate very long blocks to save tokens
        text = block.text
        if len(text) > MAX_BLOCK_TEXT_LEN:
            text = text[:MAX_BLOCK_TEXT_LEN] + "…"
        lines.append(f"[Block {block.block_id}] (Page {block.page_number}): \"{text}\"")

    return "\n".join(lines)


def _validate_classification(
    classification: dict, all_block_ids: set[int]
) -> ClassifyResponse:
    """
    Validate the AI response and ensure every block ID is accounted for.
    Missing IDs are added to UNCLASSIFIED.
    """

    shows = classification.get("shows", [])
    assignments = classification.get("assignments", {})

    # Collect all IDs the model returned
    assigned_ids: set[int] = set()
    for key, ids in assignments.items():
        # Ensure IDs are ints
        assignments[key] = [int(i) for i in ids]
        assigned_ids.update(assignments[key])

    # Find any missing block IDs
    missing = all_block_ids - assigned_ids
    if missing:
        logger.warning("AI classification missed %d block IDs: %s", len(missing), missing)
        existing_unclassified = assignments.get("UNCLASSIFIED", [])
        assignments["UNCLASSIFIED"] = existing_unclassified + sorted(missing)

    # Find any extra IDs the model hallucinated
    extra = assigned_ids - all_block_ids
    if extra:
        logger.warning("AI returned %d unknown block IDs: %s", len(extra), extra)
        for key in assignments:
            assignments[key] = [i for i in assignments[key] if i in all_block_ids]

    # Ensure GLOBAL and UNCLASSIFIED keys exist
    assignments.setdefault("GLOBAL", [])
    assignments.setdefault("UNCLASSIFIED", [])

    return ClassifyResponse(shows=shows, assignments=assignments)


async def classify_blocks(blocks: list[TextBlock]) -> ClassifyResponse:
    """
    Send text blocks to OpenAI and return a validated ClassifyResponse.
    """

    client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    model = os.environ.get("OPENAI_MODEL", "gpt-4o")

    user_message = _build_user_message(blocks)
    all_block_ids = {b.block_id for b in blocks}

    logger.info(
        "Classifying %d blocks with model '%s' (%d chars in prompt)",
        len(blocks),
        model,
        len(user_message),
    )

    response = await client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=0.1,  # Low temperature for consistent classification
    )

    raw = response.choices[0].message.content
    logger.info("Received classification response (%d chars)", len(raw))

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse AI response as JSON: %s", exc)
        # Fallback: mark everything as UNCLASSIFIED
        return ClassifyResponse(
            shows=[],
            assignments={"GLOBAL": [], "UNCLASSIFIED": sorted(all_block_ids)},
        )

    return _validate_classification(data, all_block_ids)
