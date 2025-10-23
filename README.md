# PDF API - FastAPI Interface for Payroll Extractor

A FastAPI-based REST API that provides endpoints for extracting structured payroll data from Crona Lön PDF files.

## 🎯 Purpose

This API serves as a bridge between the React/Next.js frontend (`novum-sickcalc`) and the Python-based PDF extraction engine (`payroll-extractor`). It handles PDF uploads, processes them through the extraction pipeline, and returns structured JSON data.

## 🏗️ Architecture

```
React Frontend (localhost:3000)
    ↓ HTTP POST /extract/payroll
PDF API (localhost:8000)
    ↓ extract_payroll(pdf_path)
Payroll Extractor (../payroll-extractor/)
    ↓ Structured JSON
React Frontend (displays results)
```

## 🚀 Quick Start

### Prerequisites
- Python 3.9+
- Virtual environment support
- Access to `../payroll-extractor/` directory

### Installation & Setup

1. **Navigate to the pdf-api directory:**
   ```bash
   cd pdf-api
   ```

2. **Run the startup script:**
   ```bash
   ./start.sh
   ```

   Or manually:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   python api/main.py
   ```

3. **Verify the server is running:**
   ```bash
   curl http://localhost:8000/health
   ```

## 📚 API Endpoints

### Health Check
- **GET** `/health`
- Returns server status and timestamp

### Extract Payroll Data
- **POST** `/extract/payroll`
- **Content-Type:** `multipart/form-data`
- **Body:** PDF file upload
- **Returns:** Structured JSON with payroll data

### API Documentation
- **GET** `/docs` - Interactive Swagger UI
- **GET** `/redoc` - ReDoc documentation
- **GET** `/openapi.json` - OpenAPI specification

## 📊 Response Format

### Successful Extraction
```json
{
  "203001": {
    "anstallningsnr": "203001",
    "namn": "Hanad Yusuf Sheikh",
    "loneperiod": "2025.K.05",
    "utbetalningsdag": "2025-05-23",
    "intjanandeperiod": "2025-04-01 - 2025-04-30",
    "rapporteringsperiod": "2025-04-01 - 2025-04-30",
    "adress": "Björkhyttevägen 63 C, lgh 1001",
    "ort": "71133 LINDESBERG",
    "loneposter": [
      {
        "loneart": "111",
        "benamning": "Timlön exkl. sem.ersättning [AA]",
        "antal": "70,83 tim",
        "belopp": "169,15",
        "summa": "11 980,89",
        "period": ""
      }
    ],
    "notering": "Uppdaterad efter vi fick sjukintyg 250520",
    "lonebesked": {
      "tabellskattegrund": "16 159,10",
      "engangsskattegrund": "0,00",
      "arbetsgivaravgift": "5 077,19",
      "bruttolon": "16 159,10",
      "tabellskatt": "-2 634,00",
      "engangs_frivillig_skatt": "0,00",
      "skattefritt": "0,00",
      "att_utbetala": "13 525,00"
    },
    "status": "ok"
  }
}
```

### Error Response
```json
{
  "status": "error",
  "error_message": "File must be a PDF",
  "filename": "document.txt"
}
```

## 🔧 Configuration

### CORS Settings
The API is configured to accept requests from:
- `http://localhost:3000` (React dev server)
- `http://127.0.0.1:3000`
- `http://localhost:3001` (alternative port)
- `http://127.0.0.1:3001`

### Logging
- **Console:** Structured logging with timestamps
- **File:** API requests logged to `../payroll-extractor/outbox/api_log.txt`

### Temporary Files
- All uploaded PDFs are processed in temporary files
- Files are automatically cleaned up after processing
- No permanent storage in the API directory

## 🧪 Testing

### Test with Sample PDF
```bash
curl -X POST "http://localhost:8000/extract/payroll" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@../payroll-extractor/Lönebesked_203001_2025_5.pdf"
```

### Health Check
```bash
curl http://localhost:8000/health
```

## 🛠️ Development

### Project Structure
```
pdf-api/
├── api/
│   └── main.py          # FastAPI application
├── venv/                # Virtual environment
├── requirements.txt     # Python dependencies
├── start.sh            # Startup script
├── .cursorrules        # Cursor AI rules
└── README.md           # This file
```

### Dependencies
- **FastAPI** - Web framework
- **Uvicorn** - ASGI server
- **python-multipart** - File upload support
- **pdfplumber** - PDF processing (via payroll-extractor)

### Adding New Endpoints

1. **Import required modules:**
   ```python
   from fastapi import FastAPI, File, UploadFile, HTTPException
   from fastapi.responses import JSONResponse
   ```

2. **Create endpoint function:**
   ```python
   @app.post("/extract/sickleave")
   async def extract_sickleave_endpoint(file: UploadFile = File(...)):
       # Implementation here
       pass
   ```

3. **Follow error handling pattern:**
   ```python
   try:
       # Processing logic
       return JSONResponse(result)
   except Exception as e:
       return JSONResponse(
           {"status": "error", "error_message": str(e)},
           status_code=500
       )
   ```

## 🔍 Troubleshooting

### Common Issues

1. **ModuleNotFoundError: No module named 'fastapi'**
   - Solution: Activate virtual environment: `source venv/bin/activate`

2. **ImportError: No module named 'extractor'**
   - Solution: Ensure `../payroll-extractor/` directory exists and contains `extractor/` module

3. **CORS errors in browser**
   - Solution: Check that frontend URL is in the allowed origins list

4. **Server won't start**
   - Solution: Check port 8000 is available: `lsof -i :8000`

### Logs
- **API Log:** `../payroll-extractor/outbox/api_log.txt`
- **Console:** Real-time server logs
- **Extraction Log:** `../payroll-extractor/outbox/extract_log.txt`

## 📝 Integration Notes

### With React Frontend
The API is designed to work seamlessly with the `novum-sickcalc` React application:

```javascript
// Example frontend usage
const formData = new FormData();
formData.append('file', pdfFile);

const response = await fetch('http://localhost:8000/extract/payroll', {
  method: 'POST',
  body: formData,
});

const data = await response.json();
```

### With Payroll Extractor
The API directly imports and calls the `extract_payroll()` function from the payroll-extractor module, ensuring data consistency between batch processing and API usage.

## 🚀 Production Deployment

For production deployment, consider:
- Using a production ASGI server (Gunicorn + Uvicorn workers)
- Implementing proper authentication/authorization
- Adding rate limiting
- Setting up proper logging infrastructure
- Using environment variables for configuration

## 📄 License

MIT License - see project root for details.

## 👨‍💻 Author

**Oa Berg** - Project maintainer and developer