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
import re
import io
import zipfile
import uuid
from datetime import datetime
from pypdf import PdfReader, PdfWriter

# Dynamisk sökväg till payroll-extractor
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
payroll_extractor_path = os.path.join(base_dir, "..", "payroll-extractor")
sys.path.append(os.path.abspath(payroll_extractor_path))

from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any

# Importer från extractor-modulerna
from extractor.extract_payroll import extract_payroll
from extractor.extract_payroll_from_list import process_sjuklista
from extractor.extract_payroll_prepare import split_payrolls_in_pdf, extract_employee_pdfs
import pdfplumber

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


def extract_reporting_period_from_raw(payrolls: Dict[str, Any]) -> str:
    """
    Extract 'YYYY-MM-DD - YYYY-MM-DD' from the first payroll text that contains it.
    """
    if not isinstance(payrolls, dict):
        return ""
    pattern = r"Rapporteringsperiod\s*:\s*(\d{4}-\d{2}-\d{2})\s*-\s*(\d{4}-\d{2}-\d{2})"
    for value in payrolls.values():
        if not isinstance(value, str):
            continue
        match = re.search(pattern, value)
        if match:
            return f"{match.group(1)} - {match.group(2)}"
    return ""


def extract_uppdragsgivare_from_time_report_pdf(pdf_path: str) -> str:
    """
    Extract 'Uppdragsgivare:' from the last page; fallback to all pages.
    """
    pattern = re.compile(r"Uppdragsgivare\s*:\s*([A-Za-zÅÄÖåäö\s\-]+)", re.IGNORECASE)
    with pdfplumber.open(pdf_path) as pdf:
        if len(pdf.pages) == 0:
            return ""
        last_text = pdf.pages[-1].extract_text() or ""
        match = pattern.search(last_text)
        if match:
            return match.group(1).strip()
        for page in pdf.pages:
            text = page.extract_text() or ""
            match = pattern.search(text)
            if match:
                return match.group(1).strip()
    return ""

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

        if mode == "multi":
            # Phase 2: Multi-employee PDF processing
            # Split PDF into individual payroll blocks and save raw data
            content = await file.read()
            if not content:
                error_msg = "Empty file uploaded"
                log_api_request("/extract/payroll", filename, "error", error_msg)
                raise HTTPException(status_code=400, detail=error_msg)

            now = datetime.now()
            month_dir = now.strftime("%Y_%m")
            raw_dir = os.path.join(payroll_extractor_path, "outbox", "raw", month_dir)
            os.makedirs(raw_dir, exist_ok=True)
            timestamp = now.strftime("%Y-%m-%d_%H.%M.%S")
            stable_pdf_path = os.path.join(raw_dir, f"payroll_source_{timestamp}.pdf")

            with open(stable_pdf_path, "wb") as f:
                f.write(content)

            logger.info(f"Processing PDF: {filename} (stored: {stable_pdf_path}) in {mode} mode")

            result = split_payrolls_in_pdf(stable_pdf_path)
            payrolls = result["payrolls"]

            # Save raw payroll data with PDF path metadata
            raw_file = os.path.join(raw_dir, "payroll_raw.json")
            data_to_save = {
                "pdf_path": stable_pdf_path,
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
                "message": f"Successfully processed {len(payrolls)} employees from PDF",
                "pdf_path": stable_pdf_path
            }
        else:
            # Single employee PDF processing (original behavior)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                content = await file.read()
                if not content:
                    error_msg = "Empty file uploaded"
                    log_api_request("/extract/payroll", filename, "error", error_msg)
                    raise HTTPException(status_code=400, detail=error_msg)
                tmp.write(content)
                tmp_path = tmp.name

            logger.info(f"Processing PDF: {filename} (temp: {tmp_path}) in {mode} mode")
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


@app.post("/extract/time-report-brukare")
async def extract_time_report_brukare(file: UploadFile = File(...)):
    filename = file.filename or "unknown.pdf"
    tmp_path = None

    try:
        if not filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="File must be a PDF")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            content = await file.read()
            if not content:
                raise HTTPException(status_code=400, detail="Empty PDF uploaded")
            tmp.write(content)
            tmp_path = tmp.name

        brukare = extract_uppdragsgivare_from_time_report_pdf(tmp_path)
        if not brukare:
            return JSONResponse({"status": "error", "error_message": "Uppdragsgivare not found"}, status_code=422)

        return JSONResponse({"status": "ok", "brukare": brukare})

    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Unexpected error while extracting brukare: {str(e)}"
        logger.error(error_msg)
        return JSONResponse({"status": "error", "error_message": error_msg}, status_code=500)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


# ---------------------------------------------------------
# Export ZIP package (calculation + payroll PDFs + time reports)
# ---------------------------------------------------------
@app.post("/export/zip")
async def export_zip_package(
    request: Request,
    calculation_pdf: UploadFile = File(...),
    time_report_pdf: UploadFile = File(...),
    employee_ids: str = Form(...),
    raw_file: str = Form(...)
):
    try:
        try:
            employee_list = json.loads(employee_ids)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="employee_ids must be valid JSON")

        if not isinstance(employee_list, list) or not employee_list:
            raise HTTPException(status_code=400, detail="employee_ids must be a non-empty list")

        if not os.path.exists(raw_file):
            raise HTTPException(status_code=404, detail="raw_file not found")

        with open(raw_file, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        pdf_path = raw_data.get("pdf_path") if isinstance(raw_data, dict) else None
        if not pdf_path or not os.path.exists(pdf_path):
            raise HTTPException(status_code=404, detail="payroll PDF not found for raw_file")

        payrolls_data = raw_data.get("payrolls") if isinstance(raw_data, dict) else None
        reporting_period = extract_reporting_period_from_raw(payrolls_data)
        if reporting_period:
            year_month = reporting_period.split(" - ")[0][:7]
        else:
            year_month = datetime.now().strftime("%Y-%m")
        year, month = year_month.split("-")

        zip_dir = os.path.join(payroll_extractor_path, "outbox", "zips", year, month)
        os.makedirs(zip_dir, exist_ok=True)
        zip_id = uuid.uuid4().hex
        calculation_name = calculation_pdf.filename or "berakning.pdf"
        if calculation_name.lower().endswith(".pdf"):
            zip_filename = calculation_name[:-4] + ".zip"
        else:
            zip_filename = f"{calculation_name}.zip"
        zip_path = os.path.join(zip_dir, zip_filename)
        work_dir = os.path.join(zip_dir, f"zip_{zip_id}_work")
        os.makedirs(work_dir, exist_ok=True)

        payroll_files, missing_employee_ids = extract_employee_pdfs(
            pdf_path=pdf_path,
            employee_numbers=employee_list,
            output_dir=work_dir
        )

        calc_bytes = await calculation_pdf.read()
        if not calc_bytes:
            raise HTTPException(status_code=400, detail="calculation_pdf is empty")
        time_bytes = await time_report_pdf.read()
        if not time_bytes:
            raise HTTPException(status_code=400, detail="time_report_pdf is empty")

        time_report_name = time_report_pdf.filename or "tidrapport.pdf"

        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(calculation_name, calc_bytes)
            zf.writestr(time_report_name, time_bytes)
            for anr, file_path in payroll_files.items():
                zf.write(file_path, arcname=os.path.basename(file_path))

        try:
            shutil.rmtree(work_dir)
        except Exception as e:
            logger.warning(f"Failed to clean zip work dir {work_dir}: {e}")

        download_url = str(request.base_url) + f"download/zip/{year}/{month}/{zip_filename}"
        return JSONResponse({
            "status": "ok",
            "zip_id": zip_id,
            "download_url": download_url,
            "missing_employee_ids": missing_employee_ids,
            "reporting_period": reporting_period or None
        })
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Unexpected error while creating zip: {str(e)}"
        logger.error(error_msg)
        return JSONResponse(
            {"status": "error", "error_message": error_msg},
            status_code=500
        )


# ---------------------------------------------------------
# Export merged PDF (calculation + time report + payroll PDFs)
# ---------------------------------------------------------
@app.post("/export/merged-pdf")
async def export_merged_pdf(
    request: Request,
    calculation_pdf: UploadFile = File(...),
    time_report_pdf: UploadFile = File(...),
    employee_ids: str = Form(...),
    raw_file: str = Form(...)
):
    try:
        try:
            employee_list = json.loads(employee_ids)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="employee_ids must be valid JSON")

        if not isinstance(employee_list, list) or not employee_list:
            raise HTTPException(status_code=400, detail="employee_ids must be a non-empty list")

        if not os.path.exists(raw_file):
            raise HTTPException(status_code=404, detail="raw_file not found")

        with open(raw_file, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        pdf_path = raw_data.get("pdf_path") if isinstance(raw_data, dict) else None
        if not pdf_path or not os.path.exists(pdf_path):
            raise HTTPException(status_code=404, detail="payroll PDF not found for raw_file")

        payrolls_data = raw_data.get("payrolls") if isinstance(raw_data, dict) else None
        reporting_period = extract_reporting_period_from_raw(payrolls_data)
        if reporting_period:
            year_month = reporting_period.split(" - ")[0][:7]
        else:
            year_month = datetime.now().strftime("%Y-%m")
        year, month = year_month.split("-")

        output_dir = os.path.join(payroll_extractor_path, "outbox", "zips", year, month)
        os.makedirs(output_dir, exist_ok=True)
        job_id = uuid.uuid4().hex
        calculation_name = calculation_pdf.filename or "sjukloner.pdf"
        if not calculation_name.lower().endswith(".pdf"):
            calculation_name = f"{calculation_name}.pdf"
        merged_filename = re.sub(r"^sjukloner_", "sjukloner-rapport_", calculation_name)
        merged_path = os.path.join(output_dir, merged_filename)
        work_dir = os.path.join(output_dir, f"merged_{job_id}_work")
        os.makedirs(work_dir, exist_ok=True)

        payroll_files, missing_employee_ids = extract_employee_pdfs(
            pdf_path=pdf_path,
            employee_numbers=employee_list,
            output_dir=work_dir
        )

        calc_bytes = await calculation_pdf.read()
        if not calc_bytes:
            raise HTTPException(status_code=400, detail="calculation_pdf is empty")
        time_bytes = await time_report_pdf.read()
        if not time_bytes:
            raise HTTPException(status_code=400, detail="time_report_pdf is empty")

        writer = PdfWriter()

        def append_pdf_bytes(data: bytes):
            reader = PdfReader(io.BytesIO(data))
            for page in reader.pages:
                writer.add_page(page)

        append_pdf_bytes(calc_bytes)
        append_pdf_bytes(time_bytes)

        for anr in employee_list:
            file_path = payroll_files.get(str(anr))
            if not file_path:
                continue
            with open(file_path, "rb") as f:
                reader = PdfReader(f)
                for page in reader.pages:
                    writer.add_page(page)

        with open(merged_path, "wb") as f:
            writer.write(f)

        try:
            shutil.rmtree(work_dir)
        except Exception as e:
            logger.warning(f"Failed to clean merged work dir {work_dir}: {e}")

        download_url = str(request.base_url) + f"download/merged/{year}/{month}/{merged_filename}"
        return JSONResponse({
            "status": "ok",
            "download_url": download_url,
            "missing_employee_ids": missing_employee_ids,
            "reporting_period": reporting_period or None
        })
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Unexpected error while creating merged PDF: {str(e)}"
        logger.error(error_msg)
        return JSONResponse(
            {"status": "error", "error_message": error_msg},
            status_code=500
        )


@app.get("/download/zip/{year}/{month}/{filename}")
async def download_zip_by_path(year: str, month: str, filename: str):
    zip_dir = os.path.join(payroll_extractor_path, "outbox", "zips", year, month)
    zip_path = os.path.join(zip_dir, filename)
    if not os.path.exists(zip_path):
        raise HTTPException(status_code=404, detail="zip not found")
    return FileResponse(zip_path, media_type="application/zip", filename=os.path.basename(zip_path))


@app.get("/download/merged/{year}/{month}/{filename}")
async def download_merged_pdf(year: str, month: str, filename: str):
    output_dir = os.path.join(payroll_extractor_path, "outbox", "zips", year, month)
    file_path = os.path.join(output_dir, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="merged pdf not found")
    return FileResponse(file_path, media_type="application/pdf", filename=os.path.basename(file_path))


@app.get("/download/zip/{zip_id}")
async def download_zip(zip_id: str):
    zip_dir = os.path.join(payroll_extractor_path, "outbox", "zips")
    if not os.path.exists(zip_dir):
        raise HTTPException(status_code=404, detail="zip not found")
    for root, _, files in os.walk(zip_dir):
        for file in files:
            if file == f"zip_{zip_id}.zip":
                zip_path = os.path.join(root, file)
                return FileResponse(zip_path, media_type="application/zip", filename=file)
    raise HTTPException(status_code=404, detail="zip not found")


# ---------------------------------------------------------
# Huvudkörning (lokal)
# ---------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
