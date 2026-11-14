"""FastAPI app: POST /api/review, GET /api/benchmark, serves the UI."""
from __future__ import annotations

import json

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import BENCH_DIR, MOCK, RECEIPTS_DIR, WEB_DIR
from .pipeline import review

app = FastAPI(title="Clearance", version="1.0")

# Sample chips on the home page -> files in data/receipts/
SAMPLES = {"dinner": "r21_dinner_wine.pdf", "flight": "r04_delta_flight.pdf", "saas": "r07_notion.pdf"}


@app.post("/api/review")
async def api_review(file: UploadFile | None = File(None), sample: str | None = Form(None)):
    if sample:
        name = SAMPLES.get(sample.lower())
        if not name or not (RECEIPTS_DIR / name).exists():
            raise HTTPException(404, f"unknown sample {sample}")
        data, filename = (RECEIPTS_DIR / name).read_bytes(), name
    elif file is not None:
        data, filename = await file.read(), file.filename or "upload"
    else:
        raise HTTPException(400, "send a file or a sample name")
    try:
        return review(data, filename)
    except Exception as e:
        raise HTTPException(502, f"{type(e).__name__}: {e}")


@app.get("/api/benchmark")
def api_benchmark():
    path = BENCH_DIR / "results.json"
    if not path.exists():
        return JSONResponse({"error": "no results yet: run python bench/run_bench.py"}, status_code=404)
    return json.loads(path.read_text())


@app.get("/api/health")
def health():
    return {"ok": True, "mock": MOCK}


@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/benchmark")
def benchmark_page():
    return FileResponse(WEB_DIR / "benchmark.html")


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
