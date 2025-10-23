#!/usr/bin/env python3
"""
PDF API - FastAPI interface for Payroll Extractor
==================================================

This module provides a REST API for extracting structured payroll data
from Crona Lön PDF files using the payroll-extractor module.

Endpoints:
- POST /extract/payroll: Extract payroll data from uploaded PDF
- GET /health: Health check endpoint
- GET /docs: OpenAPI documentation (FastAPI auto-generated)

Author: Oa Berg
"""

import sys
import os
import tempfile
import logging
from datetime import datetime
from typing import Dict, Any

# Dynamisk sökväg till payroll-extractor
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
payroll_extractor_path = os.path.join(base_dir, "..", "payroll-extractor")
sys.path.append(os.path.abspath(payroll_extractor_path))

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from extractor.extract_payroll import extract_payroll

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# FastAPI app with metadata
app = FastAPI(
    title="PDF API",
    description="FastAPI interface for Payroll Extractor - extracts structured data from Crona Lön PDF files",
    version="1.0.0",
    contact={
        "name": "Oa Berg",
        "email": "oa@example.com",
    },
    license_info={
        "name": "MIT",
    },
)

# CORS configuration
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

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

@app.post("/extract/payroll")
async def extract_payroll_endpoint(file: UploadFile = File(...)):
    """
    Extract payroll data from uploaded PDF file.

    Args:
        file: PDF file containing Crona Lön payroll data

    Returns:
        JSON response with extracted payroll data or error information
    """
    tmp_path = None
    filename = file.filename or "unknown.pdf"

    try:
        # Validate file type
        if not filename.lower().endswith('.pdf'):
            error_msg = "File must be a PDF"
            log_api_request("/extract/payroll", filename, "error", error_msg)
            raise HTTPException(status_code=400, detail=error_msg)

        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            content = await file.read()
            if not content:
                error_msg = "Empty file uploaded"
                log_api_request("/extract/payroll", filename, "error", error_msg)
                raise HTTPException(status_code=400, detail=error_msg)

            tmp.write(content)
            tmp_path = tmp.name

        logger.info(f"Processing PDF: {filename} (temp: {tmp_path})")

        # Extract payroll data
        result = extract_payroll(tmp_path)

        # Check if extraction was successful
        if isinstance(result, dict) and "status" in result and result["status"] == "error":
            error_msg = result.get("error_message", "Unknown extraction error")
            log_api_request("/extract/payroll", filename, "error", error_msg)
            raise HTTPException(status_code=422, detail=error_msg)

        # Log successful extraction
        log_api_request("/extract/payroll", filename, "success")
        logger.info(f"Successfully extracted payroll data from {filename}")

        return JSONResponse(result)

    except HTTPException:
        # Re-raise HTTP exceptions (already logged)
        raise
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(f"Error processing {filename}: {error_msg}")
        log_api_request("/extract/payroll", filename, "error", error_msg)

        return JSONResponse(
            {
                "status": "error",
                "error_message": error_msg,
                "filename": filename
            },
            status_code=500
        )
    finally:
        # Clean up temporary file
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
                logger.debug(f"Cleaned up temporary file: {tmp_path}")
            except Exception as e:
                logger.warning(f"Failed to remove temporary file {tmp_path}: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")

