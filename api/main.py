import sys, os
# Dynamisk sökväg till payroll-extractor
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
payroll_extractor_path = os.path.join(base_dir, "..", "payroll-extractor")
sys.path.append(os.path.abspath(payroll_extractor_path))

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse
import tempfile, os
from extractor.extract_payroll import extract_payroll  # din befintliga funktion

app = FastAPI()

from fastapi.middleware.cors import CORSMiddleware

origins = [
    "http://localhost:3000",  # din React-app
    "http://127.0.0.1:3000"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/extract/payroll")
async def extract_payroll_endpoint(file: UploadFile = File(...)):
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name

        result = extract_payroll(tmp_path)   # returnerar Python-dict
        os.remove(tmp_path)
        return JSONResponse(result)

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

