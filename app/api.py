"""
FastAPI backend.

Endpoints:
  GET  /health          -> liveness + which extractor is active
  POST /verify          -> single label: image + application fields
  POST /verify-batch    -> many images against one application spec

The backend is deliberately thin: it wires the active Extractor to the
verification engine and returns structured JSON. Latency per single request is
reported so the UI can honor the 5-second usability budget.
"""

import json
import time
from typing import Optional

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.extractors import get_extractor
from app.core.verifier import verify

app = FastAPI(title="TTB Label Verification API", version="1.0.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

_extractor = get_extractor()


def _application_from_form(
    brand_name, class_type, alcohol_content, net_contents,
    bottler_address, country_of_origin,
) -> dict:
    return {
        "brand_name": brand_name or "",
        "class_type": class_type or "",
        "alcohol_content": alcohol_content or "",
        "net_contents": net_contents or "",
        "bottler_address": bottler_address or "",
        "country_of_origin": country_of_origin or "",
    }


@app.get("/health")
def health():
    return {"status": "ok", "extractor": _extractor.name}


@app.post("/verify")
async def verify_single(
    file: UploadFile = File(...),
    brand_name: str = Form(""),
    class_type: str = Form(""),
    alcohol_content: str = Form(""),
    net_contents: str = Form(""),
    bottler_address: str = Form(""),
    country_of_origin: str = Form(""),
):
    image_bytes = await file.read()
    application = _application_from_form(
        brand_name, class_type, alcohol_content, net_contents,
        bottler_address, country_of_origin,
    )
    t0 = time.perf_counter()
    extracted = _extractor.extract(image_bytes)
    elapsed = round(time.perf_counter() - t0, 2)

    report = verify(application, extracted)
    return {
        "filename": file.filename,
        "extractor": _extractor.name,
        "elapsed_seconds": elapsed,
        "extracted": extracted,
        "report": report.to_dict(),
    }


@app.post("/verify-batch")
async def verify_batch(
    files: list[UploadFile] = File(...),
    application_json: str = Form("{}"),
):
    """Process many labels against one application spec (peak-season importers
    dumping 200-300 at once, per Sarah Chen / Janet in Seattle)."""
    try:
        application = json.loads(application_json)
    except json.JSONDecodeError:
        application = {}

    items = []
    for f in files:
        image_bytes = await f.read()
        t0 = time.perf_counter()
        extracted = _extractor.extract(image_bytes)
        elapsed = round(time.perf_counter() - t0, 2)
        report = verify(application, extracted)
        items.append({
            "filename": f.filename,
            "elapsed_seconds": elapsed,
            "overall_pass": report.overall_pass,
            "summary": report.summary,
            "report": report.to_dict(),
        })

    passed = sum(1 for i in items if i["overall_pass"])
    return {
        "extractor": _extractor.name,
        "total": len(items),
        "passed": passed,
        "failed": len(items) - passed,
        "items": items,
    }
