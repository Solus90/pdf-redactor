# PDF Redactor

Internal tool for redacting multi-show sponsorship contracts. Upload a PDF contract that covers multiple shows, classify text blocks by show using AI, and generate a permanently redacted version containing only the content for a selected show.

## How It Works

1. **Upload** a text-based PDF contract.
2. The backend extracts every text block with its page number and bounding box.
3. **Classify** — blocks are sent to OpenAI, which identifies shows and assigns each block to a show, `GLOBAL` (applies to all shows), or `UNCLASSIFIED`.
4. **Redact** — select a show; the tool keeps that show's blocks plus `GLOBAL` blocks and permanently redacts everything else using PyMuPDF redaction annotations.

## Prerequisites

- Python 3.11+
- Node.js 18+
- An OpenAI API key

## Project Structure

```
pdf-redactor/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI endpoints + in-memory store
│   │   ├── models.py        # Pydantic request/response models
│   │   ├── pdf_service.py   # PDF extraction + redaction (PyMuPDF)
│   │   └── ai_service.py    # OpenAI block classification
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── app/
│   │   ├── page.tsx          # Single-page UI
│   │   ├── layout.tsx
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
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and add your OpenAI API key

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

## Usage

1. Open `http://localhost:3000`.
2. Upload a multi-show sponsorship contract PDF.
3. Click **Classify Document** — wait for AI to process the blocks.
4. Review the detected shows and block counts.
5. Select a show from the dropdown.
6. Click **Generate Redacted PDF** — a redacted PDF will download automatically.

## API Endpoints

| Method | Endpoint         | Description                                      |
| ------ | ---------------- | ------------------------------------------------ |
| POST   | `/api/upload`    | Upload PDF, extract text blocks                  |
| POST   | `/api/classify`  | Classify blocks by show via OpenAI               |
| POST   | `/api/redact`    | Generate redacted PDF for a selected show        |

## Notes

- **MVP only** — documents are stored in memory and lost on server restart.
- **Text-based PDFs only** — scanned/image PDFs are not supported.
- Redaction is permanent: `apply_redactions()` removes the underlying text from the PDF. The redacted areas appear as black rectangles with no recoverable content.
- `UNCLASSIFIED` blocks are redacted (conservative approach).
