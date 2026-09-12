import os
import uuid
import json
from fastapi import FastAPI, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import pytesseract
from pdf2image import convert_from_path
from PIL import Image
import google.generativeai as genai

load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
model = genai.GenerativeModel("gemini-3.6-flash")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "temp"
os.makedirs(UPLOAD_DIR, exist_ok=True)

jobs = {}


import cv2
import numpy as np


def preprocess_image(pil_image: Image.Image) -> Image.Image:
    """Clean up a scanned/photographed document before OCR: greyscale,
    denoise, threshold, and deskew. Takes and returns a PIL Image."""
    img = np.array(pil_image.convert("RGB"))
    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    denoised = cv2.fastNlMeansDenoising(gray, h=10)

    thresh = cv2.adaptiveThreshold(
        denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 31, 15
    )

    # Deskew: find the angle of the text block and rotate to correct it
    coords = np.column_stack(np.where(thresh < 255))
    if len(coords) > 0:
        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle

        if abs(angle) > 0.5:  # only rotate if actually skewed
            (h, w) = thresh.shape
            center = (w // 2, h // 2)
            M = cv2.getRotationMatrix2D(center, angle, 1.0)
            thresh = cv2.warpAffine(
                thresh, M, (w, h),
                flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
            )

    return Image.fromarray(thresh)


def extract_text(file_path: str) -> str:
    """Turn a PDF or image into raw OCR text, with preprocessing applied."""
    if file_path.lower().endswith(".pdf"):
        pages = convert_from_path(file_path)
        text = ""
        for page in pages:
            cleaned = preprocess_image(page)
            text += pytesseract.image_to_string(cleaned) + "\n"
        return text
    else:
        img = Image.open(file_path)
        cleaned = preprocess_image(img)
        return pytesseract.image_to_string(cleaned)


def chunk_text(text: str, chunk_size: int = 4000, overlap: int = 200):
    """Simple manual chunker — no langchain needed."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return chunks


def ask_gemini(chunk: str) -> dict:
    prompt = f"""You are helping a patient understand a document from a hospital — this could be a
bill, a doctor's report, a prescription, discharge summary, or a mix of these. Read the OCR text below
and respond with ONLY valid JSON (no markdown, no extra text) in this exact shape:

{{
  "line_items": [{{"description": "...", "code": "...", "plain_english": "...", "amount": "..."}}],
  "total": "...",
  "health_summary": {{
    "diagnosis": "what the doctor found, in plain words, or empty string if none mentioned",
    "explanation": "2-4 sentences explaining what this means for the patient's health, calmly and clearly",
    "next_steps": ["simple, concrete follow-up actions the patient should take, if mentioned"]
  }},
  "flags": ["anything unusual, unclear, or worth double-checking"]
}}

Rules:
- If the text has billing/charge line items, fill "line_items" and "total". If not, leave line_items as [] and total as null.
- If the text has any doctor's notes, diagnosis, test results, or medical findings, fill "health_summary".
  If there's nothing medical to explain (pure billing document), leave health_summary fields as empty strings/lists.
- Write ALL explanations like you're calmly talking to a worried patient with no medical background —
  everyday words only, no jargon, no repeating clinical terms. Say "your sugar levels" not "glycemic index",
  say "an infection" not "the pathology indicates".
- Keep "plain_english" per line item under 12 words.
- Never invent information that isn't in the text. Never give medical advice beyond what the document states —
  if next steps aren't mentioned, leave next_steps empty and add a flag suggesting the patient ask their doctor directly.

OCR TEXT:
{chunk}
"""
    response = model.generate_content(prompt)
    raw = response.text.strip()

    # Gemini sometimes wraps JSON in ```json ... ``` — strip that off
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"line_items": [], "total": None, "flags": ["Could not parse this chunk"],
                "health_summary": {"diagnosis": "", "explanation": "", "next_steps": []}, "raw": raw}


def process_document(job_id: str, file_path: str):
    try:
        jobs[job_id]["status"] = "extracting_text"
        raw_text = extract_text(file_path)

        jobs[job_id]["status"] = "reasoning"
        chunks = chunk_text(raw_text)

        results = [ask_gemini(c) for c in chunks]

        merged = {"line_items": [], "total": None, "flags": [],
                  "health_summary": {"diagnosis": "", "explanation": "", "next_steps": []}}
        for r in results:
            merged["line_items"].extend(r.get("line_items", []))
            merged["flags"].extend(r.get("flags", []))
            if r.get("total"):
                merged["total"] = r["total"]

            hs = r.get("health_summary", {})
            if hs.get("diagnosis"):
                merged["health_summary"]["diagnosis"] = (
                    (merged["health_summary"]["diagnosis"] + " " + hs["diagnosis"]).strip()
                )
            if hs.get("explanation"):
                merged["health_summary"]["explanation"] = (
                    (merged["health_summary"]["explanation"] + " " + hs["explanation"]).strip()
                )
            merged["health_summary"]["next_steps"].extend(hs.get("next_steps", []))

        jobs[job_id]["status"] = "completed"
        jobs[job_id]["result"] = merged

    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)


@app.post("/upload")
async def upload_file(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    job_id = str(uuid.uuid4())
    save_path = os.path.join(UPLOAD_DIR, f"{job_id}_{file.filename}")

    with open(save_path, "wb") as f:
        f.write(await file.read())

    jobs[job_id] = {"status": "received", "filename": file.filename}

    background_tasks.add_task(process_document, job_id, save_path)

    return {"job_id": job_id, "status": "received"}


@app.get("/jobs/{job_id}")
async def get_job(job_id: str):
    if job_id not in jobs:
        return {"error": "job not found"}
    return jobs[job_id]


@app.post("/jobs/{job_id}/ask")
async def ask_question(job_id: str, question: dict):
    """Let the user ask a follow-up question about their processed bill."""
    if job_id not in jobs:
        return {"error": "job not found"}
    if jobs[job_id].get("status") != "completed":
        return {"error": "document not finished processing yet"}

    bill_data = jobs[job_id]["result"]
    user_question = question.get("question", "")

    prompt = f"""You are helping a patient understand their hospital document (bill and/or doctor's
report). Here is the extracted, structured data:

{json.dumps(bill_data)}

The patient asks: "{user_question}"

Answer in simple, friendly, everyday language — like calmly talking to a worried patient, not writing
a hospital form. Keep it short (2-4 sentences) and only use information from the data above. If the
answer isn't in the data, say you're not sure and suggest they ask their doctor or the hospital billing
desk directly. Never give new medical advice beyond what's already in the data.
"""
    response = model.generate_content(prompt)
    return {"answer": response.text.strip()}