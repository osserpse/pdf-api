# 📡 PDF API

> Ett lättviktigt REST API för att extrahera data ur PDF-filer med hjälp av `payroll-extractor`.
> Byggt med **FastAPI** och **Uvicorn**, designat för att integrera med React/Next.js.

---

## 🚀 Översikt

Detta projekt fungerar som ett gränssnitt mellan frontend och de Python-baserade extraktionsmodulerna.

### Syfte

* Ta emot PDF-filer via POST-request
* Anropa `extract_payroll()` från `payroll-extractor`
* Returnera strukturerad JSON som svar

Det är en del av ett större system:

```
React (Next.js) → PDF API (FastAPI) → Payroll Extractor (Python/pdfplumber)
```

---

## 📁 Struktur

```
pdf-api/
├── api/
│   └── main.py              ← huvudfilen för FastAPI
├── venv/                    ← virtuell miljö (rekommenderad)
├── requirements.txt
├── .gitignore
└── README.md
```

---

## ⚙️ Installation

```bash
# Klona repo
git clone https://github.com/<ditt-orgnamn>/pdf-api.git
cd pdf-api

# Skapa virtuell miljö
python3 -m venv venv
source venv/bin/activate

# Installera beroenden
pip install fastapi uvicorn pdfplumber
```

Om du även ska köra extraktionen lokalt:

```bash
pip install watchdog
```

---

## 🧩 Körning

Starta servern:

```bash
cd ~/Projects/pdf-api
source venv/bin/activate
uvicorn api.main:app --reload --port 8000
```

Servern körs då på:

```
http://127.0.0.1:8000
```

---

## 🔌 API-endpoints

### POST `/extract/payroll`

Tar emot en PDF-fil och returnerar extraherad lönedata i JSON-format.

**Exempel (curl):**

```bash
curl -X POST -F "file=@Lönebesked_203001_2025_5.pdf" http://127.0.0.1:8000/extract/payroll
```

**Svarsexempel:**

```json
{
  "203001": {
    "anstallningsnr": "203001",
    "namn": "Anders Andersson",
    "loneposter": [...],
    "lonebesked": {...},
    "status": "ok"
  }
}
```

---

## 🧪 Testa API:t

### Test via **curl**

Kör detta kommando från projektroten:

```bash
curl -X POST \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@/Users/oa/Projects/payroll-extractor/inbox/Lönebesked_203001_2025_5.pdf" \
  http://127.0.0.1:8000/extract/payroll
```

Om allt fungerar får du ett svar i terminalen som börjar med:

```json
{
  "203001": {
    "anstallningsnr": "203001",
    ...
  }
}
```

### Test via **Postman**

1. Öppna Postman och skapa en ny **POST request** till:

   ```
   http://127.0.0.1:8000/extract/payroll
   ```
2. Gå till fliken **Body → form-data**.
3. Lägg till ett fält:

   * **Key:** `file`
   * **Type:** File
   * **Value:** välj en PDF-fil (t.ex. Lönebesked_203001_2025_5.pdf)
4. Tryck **Send**.

Om allt är korrekt konfigurerat får du JSON-svaret direkt i Postman.

---

## 🧱 Arkitektur

FastAPI-appen laddar extraktorn dynamiskt:

```python
# api/main.py
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse
from extractor.extract_payroll import extract_payroll

app = FastAPI()

@app.post("/extract/payroll")
async def extract_payroll_endpoint(file: UploadFile = File(...)):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    result = extract_payroll(tmp_path)
    os.remove(tmp_path)
    return JSONResponse(result)
```

**CORS** är aktiverat för utvecklingsmiljöer:

```python
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000"
]
```

---

## 🌐 Integration med frontend

React-appen anropar API:t via `fetch()`:

```javascript
const formData = new FormData();
formData.append('file', selectedFile);

const response = await fetch('http://127.0.0.1:8000/extract/payroll', {
  method: 'POST',
  body: formData,
});

const data = await response.json();
console.log('Extracted payroll data:', data);
```

---

## 🧩 Relaterade moduler

| Modul                        | Syfte                                    | Output                 |
| ---------------------------- | ---------------------------------------- | ---------------------- |
| **Payroll Extractor**        | Extraherar PDF-lönebesked till JSON      | `payrolls.json`        |
| **Sick Leave Extractor**     | Extraherar sjuklistor (PDF/CSV) till CSV | `sickleave_YYYYMM.csv` |
| **PDF API (detta repo)**     | REST-gränssnitt mot extraktorer          | JSON-response          |
| **Frontend (Next.js/React)** | UI för uppladdning och analys            | Visar resultat         |

---

## 🧰 Felsökning

**Fel:** `ModuleNotFoundError: No module named 'extractor'`
➡️ Lägg till sökvägen till `payroll-extractor` i början av `api/main.py`:

```python
import sys, os
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
payroll_extractor_path = os.path.join(base_dir, "..", "payroll-extractor")
sys.path.append(os.path.abspath(payroll_extractor_path))
```

**Fel:** `CORS policy blocked`
➡️ Kontrollera att CORS-listan innehåller frontendens URL (`localhost:3000`).

---

## 🧩 Framtida utveckling

* ✅ Lägg till endpoint för **Sick Leave Extractor** (`/extract/sickleave`)
* 📦 Lägg till stöd för multipla PDF-uppladdningar
* 🧮 Integrera direkt med kostnadskalkylering i frontend

---

## 📜 Licens

MIT License © 2025 Happy User AB / Oa Berg

---

## 💬 Kontakt

Utvecklad av **Oa Berg**
📧 [oa@happyuser.se](mailto:oa@happyuser.se)

