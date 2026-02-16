# PDF Redactor

Internal tool for multi-show sponsorship contracts (insertion orders). Upload a PDF, extract structured data to Google Sheets (one row per insertion date), and generate redacted PDFs for individual shows so they cannot see other shows' terms or totals.

## What It Does

1. **Upload** — Accepts a text-based PDF, extracts text blocks with PyMuPDF.
2. **Export to Sheets** — Claude AI classifies blocks by show, extracts per-insertion data, and appends rows to a Google Sheet. One row per insertion date.
3. **Redact** — Generates a PDF with only one show's content visible; everything else (other shows, aggregate totals, unclassified text) is permanently redacted.

## Flow

```
Upload PDF → Export to Sheets (classify + extract) → Download Redacted PDF
```

Export runs classification internally if needed. Redact uses the classification from the prior export.

---

## Key Concepts

### Classification categories

Each text block is assigned to one category:

| Category | Kept in redacted PDF? | Purpose |
|----------|------------------------|---------|
| Show name (e.g. "Boomrazzle") | Yes, if that show is selected | Show-specific terms and line items |
| `GLOBAL` | Yes | Shared terms, signatures, party names, general clauses |
| `GLOBAL_REDACT` | **No** | Aggregate totals, combined costs, grand totals — redacted so shows can't deduce others' amounts |
| `UNCLASSIFIED` | No | Blocks the AI couldn't confidently assign |

### Row splitting (export)

- One row per **insertion date**. If a show has 22 podcast insertions, you get 22 rows.
- Podcast and newsletter billed separately → separate rows (e.g. "Boomrazzle Podcast", "Boomrazzle Newsletter").
- Podcast and newsletter billed together → one row with type `podcast and newsletter`.

### Type field

Allowed values: `podcast`, `audio`, `audio/video`, `social media`, `whitelisting`, `newsletter`, or `podcast and newsletter`. Placement details (Host-Read, Mid-Roll, 60s, etc.) go in Notes, not Type.

---

## Project Structure

```
pdf-redactor/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI app, endpoints, in-memory doc store
│   │   ├── models.py          # Pydantic models (TextBlock, ShowData, etc.)
│   │   ├── pdf_service.py     # PyMuPDF: extract blocks, redact
│   │   ├── ai_service.py      # Claude: classify blocks, extract structured data
│   │   └── sheets_service.py  # gspread: append rows to Google Sheet
│   ├── requirements.txt
│   ├── .env.example
│   └── credentials.json       # Google service account (gitignored)
├── frontend/
│   ├── app/
│   │   ├── page.tsx           # Single-page UI (upload, export, redact)
│   │   ├── layout.tsx
│   │   ├── theme.ts
│   │   └── globals.css
│   └── package.json
└── README.md
```

---

## Extending the App

### Add or change exported columns

1. **`backend/app/models.py`** — Add/update fields on `ShowData`.
2. **`backend/app/sheets_service.py`** — Update `HEADERS` and `_show_data_to_row()`.
3. **`backend/app/ai_service.py`** — Update `EXTRACTION_PROMPT` (field descriptions, JSON example) and the parsing loop in `extract_contract_data()`.

### Change extraction logic (row shape, field rules)

- **`backend/app/ai_service.py`** — Edit `EXTRACTION_PROMPT`. The AI returns JSON; the parsing loop in `extract_contract_data()` maps it to `ShowData`. The `insertion_dates` array is expanded into one `ShowData` per date.

### Change classification (what gets redacted)

- **`backend/app/ai_service.py`** — Edit `SYSTEM_PROMPT` to add categories or rules. Ensure `_validate_classification()` sets defaults for new categories.
- **`backend/app/main.py`** — Redact endpoint keeps `GLOBAL` + selected show. Other categories (e.g. `GLOBAL_REDACT`, `UNCLASSIFIED`) are redacted.

### Change which Google Sheet is used

- **`backend/.env`** — `GOOGLE_SHEET_ID` (spreadsheet ID from URL). The app always uses the first worksheet (`sheet1`). To target another sheet, modify `sheets_service.py` (`spreadsheet.sheet1` → `spreadsheet.worksheet("SheetName")`).

---

## Exported Data Columns

Each row = one insertion date. Draft Required and Requires Pixel Tracker are checkboxes (TRUE/FALSE).

| Column | Description |
|--------|-------------|
| Podcast Booked | Show/program name |
| Agency | Media buying agency |
| Advertiser | Sponsoring company/brand |
| Type | `podcast`, `audio`, `audio/video`, `social media`, `whitelisting`, `newsletter`, or `podcast and newsletter` |
| Insertion Date Per IO | Single date in MM/DD/YYYY |
| Draft Required (Y/N) | Checkbox — drafts/creative approval required |
| Impressions | Expected downloads/impressions for that insertion |
| Amount | Per-insertion net price (e.g. $4,696.25), not total |
| Payment Terms | e.g. Net 60 |
| Requires Pixel Tracker(Y/N) | Checkbox — pixel/tracking setup required |
| Notes | Anything else (placement details, makegood terms, etc.) |

---

## Setup & Run

### Prerequisites

- Python 3.11+
- Node.js 18+
- Anthropic API key (Claude)
- Google Cloud service account with Sheets API enabled

### Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env:
#   ANTHROPIC_API_KEY=sk-ant-...
#   GOOGLE_SHEET_ID=<spreadsheet-id>
#   GOOGLE_CREDENTIALS_JSON='{"type":"service_account",...}'  # or use GOOGLE_CREDENTIALS_PATH

uvicorn app.main:app --reload --port 8000
```

API: `http://localhost:8000` — Docs: `http://localhost:8000/docs`

### Frontend

```bash
cd frontend
npm install
cp .env.example .env.local   # optional; defaults to localhost:8000
npm run dev
```

Open `http://localhost:3000`.

### Google Sheets

1. Create a Google Cloud project, enable **Google Sheets API**.
2. Create a service account, download JSON key.
3. Either:
   - Put `credentials.json` in `backend/` and set `GOOGLE_CREDENTIALS_PATH=./credentials.json`, or
   - Set `GOOGLE_CREDENTIALS_JSON` to the full JSON (single line) — useful if file permissions are an issue.
4. Create a Google Sheet, share it with the service account email as **Editor**.
5. Set `GOOGLE_SHEET_ID` to the ID from the sheet URL:  
   `https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit`

**Debug:** `GET /api/sheets-check` returns connection status or error details.

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/upload` | Upload PDF, extract text blocks |
| POST | `/api/classify` | Classify blocks by show (also called internally by extract) |
| POST | `/api/extract` | Extract data, push to Google Sheets |
| POST | `/api/redact` | Generate redacted PDF for selected show |
| GET | `/api/sheets-check` | Test Google Sheets connection |

---

## Design Decisions & Gotchas

- **In-memory storage** — Documents live in `documents` dict. Restarting the backend clears them. No database.
- **Text PDFs only** — Scanned/image PDFs have no extractable text blocks. Use OCR upstream if needed.
- **Permanent redaction** — `apply_redactions()` destroys the underlying text. Redacted areas are black rectangles.
- **Append behavior** — `worksheet.append_row(..., table_range="A1")` ensures rows append after real data, not phantom rows from deleted content.
- **Credentials** — `credentials.json` and `.env` are gitignored. Use `GOOGLE_CREDENTIALS_JSON` env var if file read fails (e.g. permissions).

---

## Troubleshooting

| Issue | Check |
|-------|-------|
| "Credit balance too low" | Anthropic account — add credits at console.anthropic.com |
| "PermissionError" / "Cannot read credentials" | Use `GOOGLE_CREDENTIALS_JSON` in .env with full JSON on one line |
| "Sheets API has not been used" | Enable Google Sheets API in Cloud Console |
| "Spreadsheet not found" | Correct `GOOGLE_SHEET_ID`; sheet shared with service account |
| Data goes to wrong row | `table_range="A1"` in sheets_service; clear phantom rows in Sheet |
| AI returns invalid JSON | Prompts ask for raw JSON; `_strip_json_from_response()` removes markdown code blocks |
