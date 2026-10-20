# Setup (Windows 10/11, PowerShell)

Python 3.11 is recommended (3.10–3.13 supported). This build was developed and
tested on Python 3.13.

## 1. Clone and create a virtual environment
```powershell
cd path\to\ShivikaK-24
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

## 2. Install dependencies
```powershell
pip install -r requirements.txt
```
Optional, feature-gated extras (each enables more; the app works without them):
```powershell
pip install sentence-transformers        # local semantic embeddings + reranker
pip install docling                      # high-fidelity parser (large; pulls PyTorch)
pip install crewai                        # multi-agent orchestration (needs LLM key)
```

## 3. Configure
```powershell
Copy-Item .env.example .env
notepad .env     # set OLLAMA_API_KEY if you have one; secrets are never logged
```

## 4. Validate the environment
```powershell
python scripts\setup_check.py
```

## 5. (Optional) Qdrant
Default is **embedded on-disk** mode — no server, no Docker required.
To use a server instead:
```powershell
docker run -p 6333:6333 -v ${PWD}\data\qdrant_server:/qdrant/storage qdrant/qdrant
# then set QDRANT_MODE=server and QDRANT_URL=http://localhost:6333 in .env
```

## 6. Run the app
```powershell
streamlit run app.py
```

## 7. Tests
```powershell
pytest                       # full suite (no paid LLM calls)
python scripts\smoke_test.py # optional: requires OLLAMA_API_KEY
```

## Adding data
- **Upload:** Document Management page → upload PDF/DOCX/XLSX/CSV.
- **By URL:** Report Discovery page → paste a direct official report URL.
- **CLI:** `python scripts\ingest_reports.py --company "X Ltd" --fy FY2023-24 report.pdf`
- **Rebuild index:** delete `data\qdrant` and `data\metadata\chunks.db`, then re-ingest.

## Memory-saving settings (16 GB)
Keep `LIGHTWEIGHT_MODE=true`, `MAX_PARSE_WORKERS=1`, `EMBEDDING_PROVIDER=local`
(or `hashing`). Avoid installing Docling + MinerU together.

## Storage locations
`data\raw` (originals), `data\parsed` (markdown+json), `data\metadata`
(SQLite), `data\qdrant` (vectors), `data\evaluations`, `data\exports`.

## Troubleshooting
- *"sys.meta_path is None" on exit* — harmless Qdrant embedded finalizer.
- *Embedded Qdrant lock error* — only one process can open the on-disk store at
  once; stop other instances or use server mode.
- *Scanned PDF returns little text* — needs OCR (Docling/Tesseract); the app
  flags this rather than inventing text.
