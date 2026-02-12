"""
AI-powered block classification and data extraction using Anthropic Claude.

- classify_blocks(): Classify text blocks by show via Claude.
- extract_contract_data(): Extract structured sponsorship data per show.
"""

import json
import os
import logging

import anthropic

from app.models import TextBlock, ClassifyResponse, ShowData

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

You MUST respond with ONLY valid JSON (no markdown, no explanation) in this exact structure:
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


def _get_client() -> anthropic.AsyncAnthropic:
    """Create an Anthropic client from the configured API key."""
    return anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))


def _get_model() -> str:
    """Get the configured Claude model name."""
    return os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")


async def classify_blocks(blocks: list[TextBlock]) -> ClassifyResponse:
    """
    Send text blocks to Claude and return a validated ClassifyResponse.
    """

    client = _get_client()
    model = _get_model()

    user_message = _build_user_message(blocks)
    all_block_ids = {b.block_id for b in blocks}

    logger.info(
        "Classifying %d blocks with model '%s' (%d chars in prompt)",
        len(blocks),
        model,
        len(user_message),
    )

    response = await client.messages.create(
        model=model,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": user_message},
        ],
        temperature=0.1,  # Low temperature for consistent classification
    )

    raw = response.content[0].text
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


# ---------------------------------------------------------------------------
# Contract data extraction
# ---------------------------------------------------------------------------

EXTRACTION_PROMPT = """\
You are a contract data analyst specializing in multi-show sponsorship agreements.

You will receive the text of a sponsorship contract, along with a list of show names
that appear in the contract. For EACH show, extract the following fields from the
contract text. Use information from both show-specific sections and any general/global
sections that apply to all shows.

Fields to extract for each show:
1. sponsor_name — the sponsoring company or brand name
2. show_name — the show/program name (use the exact name provided)
3. contract_amount — the total dollar value or cost for this show's sponsorship
4. contract_terms — a brief summary of key contract terms (duration, exclusivity, etc.)
5. air_dates — the date range or flight dates when the sponsorship runs
6. cost — cost breakdown if available (e.g., per-spot cost, CPM); if same as contract_amount, repeat it
7. billing_cycle — payment terms (e.g., "Net 30", "Net 45", "Net 60", "Net 90", "Due on receipt")
8. requires_pixel_setup — "Yes", "No", or "Unknown"
9. requires_drafts — "Yes", "No", or "Unknown" (whether drafts/creative approval is required)
10. ad_frequency — how many times the ad/spot needs to run (e.g., "3x per week", "10 spots total")

Rules:
- If a field is not mentioned in the contract, use "Not specified".
- Be precise with dollar amounts — include the currency symbol.
- For dates, use a readable format (e.g., "Jan 1, 2026 – Mar 31, 2026").
- sponsor_name is typically the same across all shows in one contract.

You MUST respond with ONLY valid JSON (no markdown, no explanation) in this exact structure:
{
  "shows": [
    {
      "sponsor_name": "...",
      "show_name": "...",
      "contract_amount": "...",
      "contract_terms": "...",
      "air_dates": "...",
      "cost": "...",
      "billing_cycle": "...",
      "requires_pixel_setup": "...",
      "requires_drafts": "...",
      "ad_frequency": "..."
    }
  ]
}
"""


def _build_extraction_message(
    blocks: list[TextBlock],
    classification: ClassifyResponse,
) -> str:
    """
    Build a user message for the extraction prompt.

    For each show, include its blocks + GLOBAL blocks so the model
    has the full relevant context.
    """
    global_ids = set(classification.assignments.get("GLOBAL", []))
    blocks_by_id = {b.block_id: b for b in blocks}

    sections: list[str] = []
    sections.append(f"Shows found in this contract: {', '.join(classification.shows)}\n")
    sections.append("--- FULL CONTRACT TEXT (organized by section) ---\n")

    # Global / shared sections
    global_blocks = [blocks_by_id[bid] for bid in sorted(global_ids) if bid in blocks_by_id]
    if global_blocks:
        sections.append("== SHARED / GLOBAL SECTIONS ==")
        for b in global_blocks:
            sections.append(f"(Page {b.page_number}) {b.text}")
        sections.append("")

    # Per-show sections
    for show in classification.shows:
        show_ids = set(classification.assignments.get(show, []))
        show_blocks = [blocks_by_id[bid] for bid in sorted(show_ids) if bid in blocks_by_id]
        if show_blocks:
            sections.append(f"== SHOW: {show} ==")
            for b in show_blocks:
                sections.append(f"(Page {b.page_number}) {b.text}")
            sections.append("")

    return "\n".join(sections)


async def extract_contract_data(
    blocks: list[TextBlock],
    classification: ClassifyResponse,
) -> list[ShowData]:
    """
    Extract structured sponsorship data for each show using Claude.

    Returns a list of ShowData objects, one per show.
    """

    client = _get_client()
    model = _get_model()

    user_message = _build_extraction_message(blocks, classification)

    logger.info(
        "Extracting contract data for %d shows with model '%s' (%d chars in prompt)",
        len(classification.shows),
        model,
        len(user_message),
    )

    response = await client.messages.create(
        model=model,
        max_tokens=4096,
        system=EXTRACTION_PROMPT,
        messages=[
            {"role": "user", "content": user_message},
        ],
        temperature=0.1,
    )

    raw = response.content[0].text
    logger.info("Received extraction response (%d chars)", len(raw))

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse extraction response as JSON: %s", exc)
        raise ValueError(f"AI returned invalid JSON: {exc}") from exc

    # Parse each show into a ShowData object
    show_list = data.get("shows", [])
    result: list[ShowData] = []
    for item in show_list:
        result.append(ShowData(
            sponsor_name=item.get("sponsor_name", "Not specified"),
            show_name=item.get("show_name", "Not specified"),
            contract_amount=item.get("contract_amount", "Not specified"),
            contract_terms=item.get("contract_terms", "Not specified"),
            air_dates=item.get("air_dates", "Not specified"),
            cost=item.get("cost", "Not specified"),
            billing_cycle=item.get("billing_cycle", "Not specified"),
            requires_pixel_setup=item.get("requires_pixel_setup", "Unknown"),
            requires_drafts=item.get("requires_drafts", "Unknown"),
            ad_frequency=item.get("ad_frequency", "Not specified"),
        ))

    logger.info("Extracted data for %d shows", len(result))
    return result
