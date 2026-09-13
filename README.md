# Medical Document Translator

Turns confusing medical bills and doctor's reports into plain, everyday
language — so patients actually understand what they were charged for and
what their diagnosis means, without needing a medical or billing background.

Upload a photo or PDF of a hospital bill, prescription, or doctor's report,
and get:
- A line-by-line breakdown of charges, explained in simple words
- A plain-language summary of any diagnosis or doctor's notes found in the
  document
- Flags for anything unusual, unclear, or worth double-checking (duplicate
  charges, smudged text, conflicting totals across pages, "not a final bill"
  notices, etc.)
- A follow-up chat box to ask questions about your own document

## Why this matters

Medical bills and reports are full of jargon, codes, and abbreviations that
most patients can't parse — especially when they're already stressed about
their health. This tool acts as a first line of understanding, before a
patient needs to call their doctor or the hospital billing desk.

## How it works

1. **Upload** — user uploads a scanned image or PDF via the React frontend
   (validated for file type and a 10MB size limit before processing starts)
2. **OCR** — the backend converts PDFs to images (via Poppler) and extracts
   raw text using Tesseract OCR
3. **Image cleanup** — OpenCV preprocesses each image first (greyscale,
   denoise, adaptive threshold, deskew) to improve OCR accuracy on real,
   imperfect phone photos
4. **Chunking** — long documents are split into overlapping text chunks to
   stay within the LLM's context window
5. **Reasoning** — each chunk is sent to Google's Gemini API, which extracts
   billing line items and/or health findings into structured JSON, written
   in plain language
6. **Aggregation** — all chunk results are merged into one final result; if
   different pages report different totals, that's surfaced as a flag
   instead of silently picking one
7. **Delivery** — the frontend polls the backend every 2 seconds and renders
   the final result once processing completes
8. **Cleanup** — the uploaded file is deleted from the server as soon as
   text extraction finishes, whether it succeeded or failed
9. **Follow-up Q&A** — users can ask further questions about their own
   document, answered using only the extracted data

This asynchronous, poll-based design avoids browser timeouts during the
heavier OCR + LLM processing steps, which can take well over the standard
30-60 second HTTP timeout window.

## Tech stack

- **Frontend:** React
- **Backend:** FastAPI (Python)
- **OCR:** Tesseract OCR + pytesseract
- **PDF handling:** Poppler + pdf2image
- **Image preprocessing:** OpenCV
- **AI reasoning:** Google Gemini API (via `google-generativeai`)

## Running it locally

### Backend
```
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1        # Windows PowerShell
pip install fastapi uvicorn python-multipart pytesseract pdf2image python-dotenv google-generativeai pillow opencv-python numpy
```

Create a `backend/.env` file:
```
GOOGLE_API_KEY=your_key_here
```

You'll also need these installed system-wide, with their `bin` folders
added to your PATH:
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki)
- [Poppler](https://github.com/oschwartz10612/poppler-windows/releases)

Run the backend:
```
uvicorn main:app --reload
```

### Frontend
```
cd frontend
npm install
npm start
```

Open `http://localhost:3000`, upload a document, and watch it process.

## Privacy & safety notes

- Uploaded documents are deleted from the server immediately after text
  extraction — nothing is kept longer than needed to process it
- Only PDF, JPG, JPEG, and PNG files up to 10MB are accepted
- The AI is instructed never to invent medical advice beyond what the
  document itself states, and the UI carries a visible disclaimer that this
  tool does not replace a doctor or the hospital billing desk

## Known limitations

- OCR accuracy still depends on image quality — very blurry or heavily
  glared photos can produce incomplete text
- No persistent database yet — job data lives in memory and resets when the
  backend restarts
- Not currently deployed publicly — runs locally only, for now
