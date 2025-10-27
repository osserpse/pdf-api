#!/usr/bin/env python3
"""
PDF API - FastAPI interface for Payroll Extractor
==================================================

Endpoints:
- POST /extract/payroll: Extract payroll data from uploaded PDF
- POST /extract/sjuklista: Process uploaded CSV (Sjuklista) against payroll_raw.json
- GET /health: Health check endpoint
- GET /docs: OpenAPI documentation (FastAPI auto-generated)

Author: Oa Berg
"""

import sys
import os
import tempfile
import shutil
import logging
import json
from datetime import datetime
from typing import Dict, Any

# Dynamisk sökväg till payroll-extractor
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
payroll_extractor_path = os.path.join(base_dir, "..", "payroll-extractor")
sys.path.append(os.path.abspath(payroll_extractor_path))

from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# Importer från extractor-modulerna
from extractor.extract_payroll import extract_payroll
from extractor.extract_payroll_from_list import process_sjuklista
from extractor.extract_payroll_prepare import split_payrolls_in_pdf

# ---------------------------------------------------------
# Logging och app-inställningar
# ---------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="PDF API",
    description="FastAPI interface for Payroll Extractor - extracts structured data from Crona Lön PDF files",
    version="1.1.0",
    contact={
        "name": "Oa Berg",
        "email": "oa@example.com",
    },
    license_info={
        "name": "MIT",
    },
)

# ---------------------------------------------------------
# CORS configuration
# ---------------------------------------------------------
origins = [
    "http://localhost:3000",  # React development server
    "http://127.0.0.1:3000",
    "http://localhost:3001",  # Alternative port
    "http://127.0.0.1:3001",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------
# Hjälpfunktion för API-loggning
# ---------------------------------------------------------
def log_api_request(endpoint: str, filename: str, status: str, error_msg: str = None):
    """Log API requests to outbox/api_log.txt"""
    try:
        log_dir = os.path.join(payroll_extractor_path, "outbox")
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "api_log.txt")

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {endpoint} - {filename} - {status}"
        if error_msg:
            log_entry += f" - ERROR: {error_msg}"
        log_entry += "\n"

        with open(log_path, "a", encoding="utf-8") as f:
            f.write(log_entry)
    except Exception as e:
        logger.warning(f"Failed to write to API log: {e}")

# ---------------------------------------------------------
# API-endpoints
# ---------------------------------------------------------

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


# ---------------------------------------------------------
# PDF Extraktion (enstaka lönebesked)
# ---------------------------------------------------------
@app.post("/extract/payroll")
async def extract_payroll_endpoint(file: UploadFile = File(...), mode: str = Form("single")):
    """
    Extract payroll data from uploaded PDF file.
    Mode can be 'single' for individual payrolls or 'multi' for large PDFs with multiple employees.
    """
    tmp_path = None
    filename = file.filename or "unknown.pdf"

    try:
        if not filename.lower().endswith('.pdf'):
            error_msg = "File must be a PDF"
            log_api_request("/extract/payroll", filename, "error", error_msg)
            raise HTTPException(status_code=400, detail=error_msg)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            content = await file.read()
            if not content:
                error_msg = "Empty file uploaded"
                log_api_request("/extract/payroll", filename, "error", error_msg)
                raise HTTPException(status_code=400, detail=error_msg)
            tmp.write(content)
            tmp_path = tmp.name

        logger.info(f"Processing PDF: {filename} (temp: {tmp_path}) in {mode} mode")

        if mode == "multi":
            # Phase 2: Multi-employee PDF processing
            # Split PDF into individual payroll blocks and save raw data
            result = split_payrolls_in_pdf(tmp_path)
            payrolls = result["payrolls"]
            pdf_path = result["pdf_path"]

            # Create the raw data directory structure
            from datetime import datetime
            now = datetime.now()
            month_dir = now.strftime("%Y_%m")
            raw_dir = os.path.join(payroll_extractor_path, "outbox", "raw", month_dir)
            os.makedirs(raw_dir, exist_ok=True)

            # Save raw payroll data with PDF path metadata
            raw_file = os.path.join(raw_dir, "payroll_raw.json")
            data_to_save = {
                "pdf_path": pdf_path,
                "payrolls": payrolls
            }
            with open(raw_file, "w", encoding="utf-8") as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=2)

            logger.info(f"Created payroll_raw.json with {len(payrolls)} employees")

            result = {
                "status": "ok",
                "filename": filename,
                "mode": "multi",
                "employee_count": len(payrolls),
                "raw_file": raw_file,
                "message": f"Successfully processed {len(payrolls)} employees from PDF"
            }
        else:
            # Single employee PDF processing (original behavior)
            result = extract_payroll(tmp_path)

            if isinstance(result, dict) and "status" in result and result["status"] == "error":
                error_msg = result.get("error_message", "Unknown extraction error")
                log_api_request("/extract/payroll", filename, "error", error_msg)
                raise HTTPException(status_code=422, detail=error_msg)

        log_api_request("/extract/payroll", filename, "success")
        logger.info(f"Successfully extracted payroll data from {filename}")

        return JSONResponse(result)

    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(f"Error processing {filename}: {error_msg}")
        log_api_request("/extract/payroll", filename, "error", error_msg)
        return JSONResponse(
            {"status": "error", "error_message": error_msg, "filename": filename},
            status_code=500
        )
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
                logger.debug(f"Cleaned up temporary file: {tmp_path}")
            except Exception as e:
                logger.warning(f"Failed to remove temporary file {tmp_path}: {e}")


# ---------------------------------------------------------
# CSV Sjuklista-extraktion (batch mot senaste raw/)
# ---------------------------------------------------------
@app.post("/extract/sjuklista")
async def extract_from_sjuklista(file: UploadFile = File(...)):
    """
    Process a Sjuklista CSV file and extract payroll data
    from the latest available payroll_raw.json dataset.
    """
    filename = file.filename or "unknown.csv"
    tmp_path = None

    try:
        if not filename.lower().endswith('.csv'):
            error_msg = "File must be a CSV"
            log_api_request("/extract/sjuklista", filename, "error", error_msg)
            raise HTTPException(status_code=400, detail=error_msg)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
            content = await file.read()
            if not content:
                error_msg = "Empty CSV uploaded"
                log_api_request("/extract/sjuklista", filename, "error", error_msg)
                raise HTTPException(status_code=400, detail=error_msg)
            tmp.write(content)
            tmp_path = tmp.name

        logger.info(f"Processing sjuklista: {filename} (temp: {tmp_path})")

        # Anropa den batch-baserade extraktionen
        # Use the correct outbox directory path (payroll-extractor/outbox)
        correct_outbox_dir = os.path.join(payroll_extractor_path, "outbox")
        results = process_sjuklista(tmp_path, outbox_dir=correct_outbox_dir)

        log_api_request("/extract/sjuklista", filename, "success")
        logger.info(f"✅ Successfully extracted payroll data for sjuklista {filename}")

        return JSONResponse({
            "status": "ok",
            "filename": filename,
            "count": len(results),
            "results": results
        })

    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Unexpected error while processing sjuklista: {str(e)}"
        logger.error(error_msg)
        log_api_request("/extract/sjuklista", filename, "error", error_msg)
        raise HTTPException(status_code=500, detail=error_msg)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
                logger.debug(f"Removed temp file: {tmp_path}")
            except Exception as e:
                logger.warning(f"Failed to remove temp file {tmp_path}: {e}")


# ---------------------------------------------------------
# Huvudkörning (lokal)
# ---------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
