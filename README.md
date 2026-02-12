# PDF Redactor

Internal tool for redacting multi-show sponsorship contracts and extracting structured data to Google Sheets. Upload a PDF contract that covers multiple shows, classify text blocks by show using AI, generate a permanently redacted version for a single show, and export sponsor details to a spreadsheet.

## How It Works

1. **Upload** a text-based PDF contract.
2. The backend extracts every text block with its page number and bounding box.
3. **Classify** — blocks are sent to OpenAI, which identifies shows and assigns each block to a show, `GLOBAL` (applies to all shows), or `UNCLASSIFIED`.
4. **Redact** — select a show; the tool keeps that show's blocks plus `GLOBAL` blocks and permanently redacts everything else using PyMuPDF redaction annotations.
5. **Export to Sheets** — extract structured data (sponsor name, costs, billing cycle, air dates, etc.) for each show and push it directly to a Google Sheet.

## Prerequisites

- Python 3.11+
- Node.js 18+
- An OpenAI API key
- A Google Cloud service account with Sheets API access (for the export feature)

## Project Structure

```
pdf-redactor/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI endpoints + in-memory store
│   │   ├── models.py          # Pydantic request/response models
│   │   ├── pdf_service.py     # PDF extraction + redaction (PyMuPDF)
│   │   ├── ai_service.py      # OpenAI classification + data extraction
│   │   └── sheets_service.py  # Google Sheets integration (gspread)
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── app/
│   │   ├── page.tsx           # Single-page UI
│   │   ├── layout.tsx
│   │   ├── theme.ts           # Material UI theme
│   │   ├── ThemeRegistry.tsx   # MUI + Next.js provider
│   │   └── globals.css
│   ├── .env.example
│   └── package.json
└── README.md
```

## Setup & Run

### Backend

```bash
cd backend

# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and add your OpenAI API key (required)
# Edit .env and add Google Sheets credentials (required for export feature)

# Start the server
uvicorn app.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Configure environment (optional — defaults to http://localhost:8000)
cp .env.example .env.local

# Start the dev server
npm run dev
```

Open `http://localhost:3000` in your browser.

### Google Sheets Setup

The export feature requires a Google Cloud service account. Follow these steps:

1. **Create a Google Cloud project** (or use an existing one) at [console.cloud.google.com](https://console.cloud.google.com).

2. **Enable the Google Sheets API** in the project's API library.

3. **Create a service account**:
   - Go to IAM & Admin > Service Accounts.
   - Create a new service account (no special roles needed).
   - Create a JSON key and download it.

4. **Place the credentials file** in the `backend/` directory (e.g., `backend/credentials.json`).

5. **Create a Google Sheet** (or use an existing one) where data will be exported.

6. **Share the sheet** with the service account's email address (found in the JSON file as `client_email`). Give it **Editor** access.

7. **Update `backend/.env`**:
   ```
   GOOGLE_CREDENTIALS_PATH=./credentials.json
   GOOGLE_SHEET_ID=your-spreadsheet-id-here
   ```
   The spreadsheet ID is the long string in the Google Sheet URL:
   `https://docs.google.com/spreadsheets/d/SPREADSHEET_ID_HERE/edit`

## Usage

1. Open `http://localhost:3000`.
2. Upload a multi-show sponsorship contract PDF.
3. Click **Scan document** — wait for AI to identify the shows.
4. Review the detected shows and section counts.
5. **Redact**: Select a show from the dropdown and click **Download PDF**.
6. **Export**: Click **Export to Sheets** to push structured data (sponsor, costs, billing, dates, etc.) to your Google Sheet.

## Exported Data Columns

Each row in the Google Sheet represents one show from one contract:

| Column | Description |
| --- | --- |
| Sponsor Name | The sponsoring company or brand |
| Show Name | The program/show name |
| Contract Amount | Total dollar value |
| Contract Terms | Summary of key terms |
| Air Dates / Flight Dates | Date range the sponsorship runs |
| Cost | Cost breakdown (per-spot, CPM, etc.) |
| Billing Cycle | Payment terms (Net 30, Net 60, etc.) |
| Requires Pixel Setup | Yes / No / Unknown |
| Requires Drafts | Yes / No / Unknown |
| Ad Frequency | How many times ads need to run |

## API Endpoints

| Method | Endpoint         | Description                                      |
| ------ | ---------------- | ------------------------------------------------ |
| POST   | `/api/upload`    | Upload PDF, extract text blocks                  |
| POST   | `/api/classify`  | Classify blocks by show via OpenAI               |
| POST   | `/api/redact`    | Generate redacted PDF for a selected show        |
| POST   | `/api/extract`   | Extract data and push to Google Sheets           |

## Notes

- **MVP only** — documents are stored in memory and lost on server restart.
- **Text-based PDFs only** — scanned/image PDFs are not supported.
- Redaction is permanent: `apply_redactions()` removes the underlying text from the PDF. The redacted areas appear as black rectangles with no recoverable content.
- `UNCLASSIFIED` blocks are redacted (conservative approach).
- The Google Sheets export appends rows — it does not overwrite existing data.
- Add `credentials.json` to your `.gitignore` to avoid committing secrets.
