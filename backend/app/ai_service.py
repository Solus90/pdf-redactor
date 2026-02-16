"""
AI-powered block classification and data extraction using Anthropic Claude.

- classify_blocks(): Classify text blocks by show via Claude.
- extract_contract_data(): Extract structured sponsorship data per show.
"""

import json
import os
import re
import logging

import anthropic

from app.models import TextBlock, ClassifyResponse, ShowData

logger = logging.getLogger(__name__)


def _strip_json_from_response(raw: str) -> str:
    """Strip markdown code blocks from AI response to get raw JSON."""
    if not raw or not raw.strip():
        return "{}"
    text = raw.strip()
    if text.startswith("```"):
        match = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", text, re.DOTALL)
        if match:
            text = match.group(1).strip()
        else:
            text = re.sub(r"^```\w*\n?", "", text)
            text = re.sub(r"\n?```\s*$", "", text).strip()
    return text


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
   - "GLOBAL" — if the block applies to ALL shows AND does NOT contain
     financial figures (e.g., general terms, signatures, party names,
     dates, governing law, universal clauses).
   - "GLOBAL_REDACT" — if the block applies to all shows BUT contains
     total contract amounts, aggregate dollar figures, combined costs,
     grand totals, overall budget summaries, or any financial information
     that spans multiple shows. These blocks will be redacted so that
     individual shows cannot calculate what other shows are being paid.
   - "UNCLASSIFIED" — if you cannot confidently determine which show
     the block belongs to.

Rules:
- Every block ID must appear in exactly one category.
- Show names should be normalized (consistent capitalization/spelling).
- Section headers that introduce a show-specific section belong to that show.
- Shared header/footer text, preamble, and signature blocks are GLOBAL.
- Any block mentioning a total/combined/aggregate dollar amount that covers
  more than one show MUST be classified as GLOBAL_REDACT, not GLOBAL.

You MUST respond with ONLY valid JSON (no markdown, no explanation) in this exact structure:
{
  "shows": ["Show Name A", "Show Name B"],
  "assignments": {
    "Show Name A": [1, 3, 5],
    "Show Name B": [2, 4, 6],
    "GLOBAL": [0, 7, 8],
    "GLOBAL_REDACT": [10, 11],
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

    # Ensure GLOBAL, GLOBAL_REDACT, and UNCLASSIFIED keys exist
    assignments.setdefault("GLOBAL", [])
    assignments.setdefault("GLOBAL_REDACT", [])
    assignments.setdefault("UNCLASSIFIED", [])

    return ClassifyResponse(shows=shows, assignments=assignments)


def _get_client() -> anthropic.AsyncAnthropic:
    """Create an Anthropic client from the configured API key."""
    return anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))


def _get_model() -> str:
    """Get the configured Claude model name."""
    return os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-6")


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

    text = _strip_json_from_response(raw)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse AI response as JSON: %s. Raw (first 300 chars): %r", exc, (raw or "")[:300])
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
You are a contract data analyst specializing in multi-show sponsorship contracts
(insertion orders). You will receive the text of a contract along with a list of
show names. Your job is to extract structured data and produce ONE ROW per
separately-billed line item.

IMPORTANT — Row-splitting rules:
- Each show/program name gets its own row.
- If a single show has MULTIPLE media types that are billed separately
  (e.g., podcast line items AND newsletter line items with separate costs),
  create a SEPARATE row for each media type, even if they share the same
  show name. Use the show name for podcast_booked in both rows.
- If a single show's podcast and newsletter are billed TOGETHER (one combined
  cost), produce ONE row and set the type to "podcast and newsletter".

Fields to extract for each row:
1. podcast_booked — the show/program name
2. agency — the media buying agency or agency of record
3. advertiser — the sponsoring company or brand name
4. type — MUST be one of: "podcast", "audio", "audio/video", "social media",
   "whitelisting", "newsletter", or a combination like "podcast and newsletter"
   when billed together. Do NOT use ad-format descriptions like "Host-Read",
   "Mid-Roll", "60s", "Embedded", or "Evergreen" — those are placement details,
   not the type.
5. insertion_dates — a JSON array of objects, one per insertion date. Each object
   has "date" (MM/DD/YYYY) and "amount" (the net price for THAT single insertion,
   e.g. "$6,000" or "$0"). List every insertion individually.
6. draft_required_yn — "Y" or "N"
7. impressions — the number of expected downloads/impressions for this insertion
   (e.g., "600,000", "361,250", "22,500"). Use the number from the contract.
8. payment_terms — payment terms (e.g., "Net 60")
9. requires_pixel_tracker_yn — "Y" or "N"
10. notes — any relevant details that don't fit in other fields (e.g., placement
    info like "Mid-Roll, 60s, Baked-in", impression targets, makegood terms,
    exclusivity clauses, cancellation terms). Use "" if nothing notable.

Rules:
- If a field is not mentioned in the contract, use "Not specified".
- For draft_required_yn and requires_pixel_tracker_yn, use only "Y" or "N";
  use "N" if unknown.
- Be precise with dollar amounts — use the per-insertion net price, NOT the
  total across all insertions.
- insertion_dates MUST be a JSON array of {"date": "MM/DD/YYYY", "amount": "$X"}.
  For date ranges like "1/14-1/19/2026", pick the start date: "01/14/2026".
- Advertiser is typically the same across all rows.

You MUST respond with ONLY raw JSON—no markdown code blocks, no backticks, no explanation. Start directly with { and end with }.
{
  "shows": [
    {
      "podcast_booked": "...",
      "agency": "...",
      "advertiser": "...",
      "type": "podcast",
      "insertion_dates": [
        {"date": "03/02/2026", "amount": "$6,000"},
        {"date": "04/01/2026", "amount": "$6,000"}
      ],
      "draft_required_yn": "Y or N",
      "impressions": "600,000",
      "payment_terms": "...",
      "requires_pixel_tracker_yn": "Y or N",
      "notes": "..."
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

    if not raw or not raw.strip():
        logger.error("AI returned empty extraction response")
        raise ValueError("AI returned an empty response. Try again or use a different PDF.")

    text = _strip_json_from_response(raw)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse extraction response: %s. Raw (first 500 chars): %r", exc, raw[:500])
        raise ValueError(f"AI returned invalid JSON: {exc}. Try uploading again.") from exc

    # Parse each show into ShowData objects — one row per insertion date
    show_list = data.get("shows", [])
    result: list[ShowData] = []
    for item in show_list:
        base = dict(
            podcast_booked=item.get("podcast_booked", "Not specified"),
            agency=item.get("agency", "Not specified"),
            advertiser=item.get("advertiser", "Not specified"),
            type=item.get("type", "Not specified"),
            draft_required_yn=item.get("draft_required_yn", "N"),
            impressions=item.get("impressions", "Not specified"),
            payment_terms=item.get("payment_terms", "Not specified"),
            requires_pixel_tracker_yn=item.get("requires_pixel_tracker_yn", "N"),
            notes=item.get("notes", ""),
        )

        insertions = item.get("insertion_dates", [])
        # Fallback: old format with insertion_date_per_io
        if not insertions:
            old_dates = item.get("insertion_date_per_io", [])
            old_amount = item.get("amount", "Not specified")
            if isinstance(old_dates, str):
                old_dates = [old_dates] if old_dates else ["Not specified"]
            insertions = [{"date": d, "amount": old_amount} for d in old_dates]
        if not insertions:
            insertions = [{"date": "Not specified", "amount": "Not specified"}]

        for ins in insertions:
            if isinstance(ins, dict):
                date = ins.get("date", "Not specified")
                amount = ins.get("amount", "Not specified")
            else:
                date = str(ins)
                amount = "Not specified"
            result.append(ShowData(
                insertion_date_per_io=date,
                amount=amount,
                **base,
            ))

    logger.info("Extracted data for %d rows (%d shows expanded by date)", len(result), len(show_list))
    return result
