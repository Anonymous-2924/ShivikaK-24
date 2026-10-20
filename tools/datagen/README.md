# tools/datagen/ — standalone apparel data generator

**Standalone.** No imports from `src/`. Enforced by:
1. ruff `flake8-tidy-imports` rule in `pyproject.toml`
2. `tests/test_datagen_standalone.py` which AST-walks every file here

Writes to `generated_data/` (gitignored). The app never touches that
directory. **You** move files from there into `data/inbox/` manually when
you want them ingested.

## Running

```bash
# Default: 500 tier-1 + 200 tier-2 suppliers, 2000 SKUs, 5000 components,
# 80 plants, 60 routes. Writes ~180 files, ~11MB, in ~2 seconds.
python -m tools.datagen.generate --suppliers 500 --skus 2000 --seed 42

# Tiny run for CI / local dev.
python -m tools.datagen.generate --smoke --seed 42 --out /tmp/dg

# Full flag set.
python -m tools.datagen.generate --help
```

Deterministic given a seed. Running twice with the same `--seed` produces
byte-identical plain-text output (CSV, JSON, XML, Markdown, `REALISM_LOG.md`);
PDF/XLSX/DOCX files share the same *content* but their file headers embed
timestamps so byte-level diffs will show noise — the Phase 2 tests only
assert plain-text determinism.

## What it emits (apparel / fast-fashion domain)

| Dir / file                        | Format    | Purpose                                                          |
|-----------------------------------|-----------|------------------------------------------------------------------|
| `supplier_master.xlsx`            | xlsx      | 3 sheets: Tier-1, Tier-2, Addresses. Near-duplicates interleaved |
| `bom_master.xlsx`                 | xlsx      | BOM per SKU with MERGED headers and `=SUM()` formulas; one malformed sheet |
| `inventory_snapshot.xlsx`         | xlsx      | On-hand + in-transit per SKU per plant                           |
| `pricelist.xlsx`                  | xlsx      | 3 sheets by season; AW26 contains unlabelled-currency mess       |
| `shipments/shipment_log.csv`      | csv       | ~8000 shipment lines; mixed kg/lb columns; mixed currencies      |
| `shipments/lead_time_history.csv` | csv       | 18 months × tier-1 suppliers                                     |
| `demand/daily_demand_YYYY-MM.csv` | csv × 12  | Monthly daily-sales dumps                                        |
| `audits/*.pdf`                    | pdf       | Supplier audit reports with embedded findings tables; some OCR-noised |
| `contracts/*.pdf`                 | pdf       | Master Supply Agreements, prose-heavy                            |
| `certifications/*.pdf`            | pdf       | GOTS / OEKO-TEX / BSCI / ISO certificates                        |
| `compliance/*.pdf`                | pdf       | Modern Slavery statement etc.                                    |
| `financials/*.pdf` and `*.xlsx`   | both      | Per-supplier simplified P&L + balance sheet in both formats      |
| `policies/*.docx`                 | docx      | Code of Conduct, RSL, Chemical Management, ESG Audit Framework   |
| `correspondence/*.docx`           | docx      | Supplier email threads about delays                              |
| `postmortems/*.docx`              | docx      | Incident write-ups                                               |
| `erp/*.json` and `plants_export.xml` | json/xml | ERP-style structured exports                                   |
| `news/news_###_<cat>.{md,txt}`    | md / txt  | Disruption news corpus (flood, fire, strike, customs, quality, ESG) |
| `charts/*.png`                    | png       | Bar-chart screenshots for vision-extraction tests                |
| `REALISM_LOG.md`                  | md        | **Answer sheet** — every piece of mess, categorised              |

## Mess injected (targets vs. what the default seed actually produced)

| Category                                | Target     | Seed 42 (500 suppliers) |
|-----------------------------------------|------------|-------------------------|
| Supplier missing-field rate             | ~5%        | 5.3% (37/700)           |
| Supplier stale-record rate              | ~3%        | 3.9% (27/700)           |
| Near-duplicate suppliers (same tax ID)  | ~2%        | 18                      |
| Contradictory capacity figures          | 10         | 10                      |
| Name-variant usages across documents    | hundreds   | 447                     |
| Deliberately malformed tables           | ≥1         | 1                       |
| OCR-style noise injections              | some       | 17 audit reports        |
| Unlabelled-currency price rows          | some       | 818                     |
| Shipment rows with weight only in `lb`  | ~10%       | 803 (~10%)              |

The `REALISM_LOG.md` is the **ground truth** for Phase 6 evaluation —
a working ingest should surface most of this as either review-queue
candidates, low-confidence edges, or validator warnings.

## Dependencies

Comes in via the `datagen` extra (`pip install -e ".[datagen]"`):
`faker`, `reportlab`. Pillow arrives transitively via reportlab.
`openpyxl` and `python-docx` are in the main project deps.
