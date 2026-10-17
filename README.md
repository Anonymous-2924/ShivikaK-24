## Hi, I'm Shivika Khanna 👋

**PGDM – Business Data Analytics** @ FORE School of Management, New Delhi (2025–27), with a secondary focus in **Finance & Accounting**.

I work at the intersection of **finance, analytics, and AI** — turning messy, real-world data into decisions a business can actually act on. I'm just as comfortable reading a company's financial statements as I am building a Power BI model or wiring up an automation workflow.

### 🛠️ What I work with
- **Analytics & BI:** Power BI (DAX, data modelling), Advanced Excel, SQL
- **Finance:** Financial statement analysis, three-statement modelling, DCF valuation · NISM-certified
- **Python & AI:** Python for data analysis, RAG pipelines, n8n workflow automation, Docker

### 📂 What you'll find here
Projects that show how I think — from financial-performance analysis of a listed company to applied AI and automation builds.

### 📫 Reach me
https://www.linkedin.com/in/shivika-khanna-772ab8211/ · 065049@fsm.ac.in

---

# 📊 FinSight AI — Financial Intelligence & Annual Report Analyst

A financial research assistant for **Indian listed companies**. It parses
annual reports, indexes them for Retrieval-Augmented Generation, computes
financial metrics deterministically, and answers research questions with
**source citations** — clearly separating reported facts, calculated metrics,
AI interpretation, and missing/conflicting information. It **never invents**
figures, pages, quotes or reports.

## Highlights
- **Streamlit dashboard** (7 pages): Dashboard, Company Explorer, Report
  Discovery, Document Management, AI Research, Financial Analysis, Settings.
- **RAG**: structure-aware chunking → embeddings → **Qdrant** vectors →
  **hybrid retrieval** (real BM25 + Reciprocal Rank Fusion) → citations.
- **Deterministic finance engine** (the LLM never does the arithmetic) with
  per-input provenance, divide-by-zero / mixed-basis / missing-data guards.
- **Multi-agent research** (CrewAI: planner → researcher → analyst → citation
  reviewer) with a deterministic fallback orchestrator when CrewAI/LLM are
  absent.
- **Anti-hallucination**: quote/number grounding checks and honest abstention.
- **Ollama Cloud** LLM integration (configurable, retries/backoff, auth &
  rate-limit handling); the app stays usable (evidence-only) without a key.
- **Graceful degradation** for a 16 GB machine: works without Docling, without
  sentence-transformers (hashing fallback), without Docker (embedded Qdrant).

## Quickstart
```bash
pip install -r requirements.txt
cp .env.example .env            # optional: set OLLAMA_API_KEY
python scripts/setup_check.py   # validate environment (no secrets printed)
streamlit run app.py
pytest                          # 48 tests, no paid LLM calls
```
Windows PowerShell instructions: **[docs/setup.md](docs/setup.md)**.

## Documentation
- [Architecture](docs/architecture.md) ·
  [Decisions (ADRs)](docs/architecture_decisions.md)
- [Setup (Windows)](docs/setup.md) · [Data sources policy](docs/data_sources.md)
- [Vector store comparison](docs/vector_store_comparison.md) ·
  [Evaluation](docs/evaluation.md) · [Limitations](docs/limitations.md)

## What is verified vs. requires configuration
Tests pass locally (Python 3.13): finance engine, validation/dedup, chunking,
citations/grounding, hybrid retrieval, SQLite stores, **end-to-end ingest →
retrieve with persistence across restart**, PDF parsing, Ollama error-handling
(mocked), and the Streamlit app serving all pages. Cloud LLM generation,
Docling, local embeddings, the CrewAI LLM crew and official-source scraping
require external setup or are intentionally optional — see
[docs/limitations.md](docs/limitations.md).

> FinSight AI was scaffolded as an applied-AI project in this repository.
> It is a functional MVP, not a production-audited system.
