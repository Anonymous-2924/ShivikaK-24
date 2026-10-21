"""Orchestrator for the standalone apparel / fast-fashion data generator.

Deterministic given --seed. Writes all output under --out (default
``generated_data/``). The app never touches this directory; the user
copies files from here into ``data/inbox/``.
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

from tools.datagen import entities, mess
from tools.datagen.realism_log import RealismLog
from tools.datagen.writers import (
    charts,
    csv_writer,
    docx_writer,
    excel,
    news,
    pdf_writer,
    structured,
)

POLICY_DOCS = [
    ("Supplier_Code_of_Conduct.docx",
     "Supplier Code of Conduct", [
        "All suppliers must comply with applicable local labour laws, "
        "including minimum wage and maximum working-hour provisions.",
        "Suppliers shall maintain documented procedures for grievance "
        "handling, with anonymous reporting channels for workers.",
        "Subcontracting to undisclosed facilities is a material breach of "
        "this Code and the Master Supply Agreement.",
     ]),
    ("Restricted_Substances_List.docx",
     "Restricted Substances List v3.2", [
        "The following substances are restricted at the stated maximum "
        "concentrations in finished garments and packaging materials. "
        "The list is updated quarterly in line with REACH Annex XVII and "
        "the OEKO-TEX Standard 100 limit values.",
        "Testing to ISO 17025-accredited methods is required on 100% of "
        "colour-ways for buyers' own-label programmes.",
     ]),
    ("Chemical_Management_Policy.docx",
     "Chemical Management Policy", [
        "Tier-2 suppliers performing wet processing (dyeing, printing, "
        "finishing) shall implement the ZDHC MRSL and submit quarterly "
        "ZDHC Gateway results.",
        "A chemical inventory must be maintained on-site, with safety "
        "data sheets accessible in the local language.",
     ]),
    ("ESG_Audit_Framework.docx",
     "ESG Audit Framework (2026)", [
        "This framework replaces the 2024 version. It introduces living-"
        "wage benchmarking, water-withdrawal reporting, and scope-3 "
        "emissions tracking for tier-2 suppliers.",
     ]),
]


def _parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="tools.datagen.generate",
                                description="Apparel supply-chain data generator")
    p.add_argument("--suppliers", type=int, default=500,
                   help="Approx tier-1 supplier count (default 500).")
    p.add_argument("--tier2", type=int, default=0,
                   help="Tier-2 supplier count. If 0, derived as suppliers*0.4.")
    p.add_argument("--plants", type=int, default=0,
                   help="Plant count. If 0, derived as suppliers*0.16.")
    p.add_argument("--components", type=int, default=5000)
    p.add_argument("--skus", type=int, default=2000)
    p.add_argument("--routes", type=int, default=60)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", default="generated_data")
    p.add_argument("--audit-reports", type=int, default=30,
                   help="How many supplier audit PDFs to produce.")
    p.add_argument("--financials-pdf", type=int, default=20)
    p.add_argument("--financials-xlsx", type=int, default=20)
    p.add_argument("--contracts", type=int, default=10)
    p.add_argument("--certification-pdfs", type=int, default=15)
    p.add_argument("--news-articles", type=int, default=30)
    p.add_argument("--correspondence", type=int, default=15)
    p.add_argument("--postmortems", type=int, default=5)
    p.add_argument("--charts", type=int, default=8)
    p.add_argument("--shipment-rows", type=int, default=8000)
    p.add_argument("--smoke", action="store_true",
                   help="Tiny run for CI: ignores most counts and overrides "
                        "sizes to a few of each type.")
    return p.parse_args()


def _smoke(ns: argparse.Namespace) -> None:
    ns.suppliers = 20
    ns.tier2 = 8
    ns.plants = 6
    ns.components = 60
    ns.skus = 40
    ns.routes = 8
    ns.audit_reports = 3
    ns.financials_pdf = 2
    ns.financials_xlsx = 2
    ns.contracts = 2
    ns.certification_pdfs = 2
    ns.news_articles = 4
    ns.correspondence = 2
    ns.postmortems = 1
    ns.charts = 3
    ns.shipment_rows = 200


def main() -> int:
    ns = _parse()
    if ns.smoke:
        _smoke(ns)
    if ns.tier2 == 0:
        ns.tier2 = max(1, int(ns.suppliers * 0.4))
    if ns.plants == 0:
        ns.plants = max(1, int(ns.suppliers * 0.16))

    rng = random.Random(ns.seed)
    log = RealismLog()
    t0 = time.monotonic()

    out = Path(ns.out)
    out.mkdir(parents=True, exist_ok=True)
    # Clear leftovers from a previous run — same seed should produce identical
    # output, but a different seed shouldn't leave stale files behind.
    for sub in ("audits", "contracts", "certifications", "compliance",
                "policies", "correspondence", "postmortems", "financials",
                "erp", "news", "charts", "shipments", "demand"):
        (out / sub).mkdir(parents=True, exist_ok=True)

    print(f"[datagen] seed={ns.seed}  suppliers={ns.suppliers}  tier2={ns.tier2}  "
          f"plants={ns.plants}  components={ns.components}  skus={ns.skus}  "
          f"routes={ns.routes}", file=sys.stderr)

    # 1. Populate entities deterministically.
    pop = entities.populate(
        rng,
        n_tier1=ns.suppliers, n_tier2=ns.tier2, n_plants=ns.plants,
        n_components=ns.components, n_skus=ns.skus, n_routes=ns.routes,
    )
    print(f"[datagen] populated: {len(pop.suppliers)} suppliers, "
          f"{len(pop.plants)} plants, {len(pop.components)} components, "
          f"{len(pop.skus)} skus, {len(pop.routes)} routes",
          file=sys.stderr)

    # 2. Inject mess.
    mess.flag_missing_fields(pop, rng, log)
    mess.flag_stale(pop, rng, log)
    extras = mess.inject_near_duplicate_suppliers(pop, rng, log)
    contradiction_pairs = dict(mess.inject_contradiction(pop, rng, log, n=10))

    # 3. Writers.
    print("[datagen] writing supplier_master.xlsx", file=sys.stderr)
    excel.write_supplier_master(out / "supplier_master.xlsx", pop, extras, rng, log)
    print("[datagen] writing bom_master.xlsx", file=sys.stderr)
    excel.write_bom_master(out / "bom_master.xlsx", pop, rng, log)
    print("[datagen] writing inventory_snapshot.xlsx", file=sys.stderr)
    excel.write_inventory_snapshot(out / "inventory_snapshot.xlsx", pop, rng, log)
    print("[datagen] writing pricelist.xlsx (multi-sheet)", file=sys.stderr)
    excel.write_pricelist(out / "pricelist.xlsx", pop, rng, log)

    print(f"[datagen] writing shipment log ({ns.shipment_rows} rows)", file=sys.stderr)
    csv_writer.write_shipment_log(out / "shipments" / "shipment_log.csv",
                                   pop, rng, log, n_rows=ns.shipment_rows)
    csv_writer.write_lead_time_history(out / "shipments" / "lead_time_history.csv",
                                        pop, rng, log)
    print("[datagen] writing daily demand (12 months)", file=sys.stderr)
    csv_writer.write_daily_demand(out / "demand", pop, rng, log)

    print(f"[datagen] writing {ns.audit_reports} audit PDFs", file=sys.stderr)
    chosen_t1 = [s for s in pop.suppliers if s.tier == 1][: ns.audit_reports]
    for s in chosen_t1:
        alt = contradiction_pairs.get(s.id)
        pdf_writer.write_audit_report(out / "audits" / f"audit_{s.id}.pdf",
                                       s, pop, alt, rng, log)

    print(f"[datagen] writing {ns.contracts} contracts", file=sys.stderr)
    for s in chosen_t1[: ns.contracts]:
        pdf_writer.write_contract(out / "contracts" / f"contract_{s.id}.pdf",
                                   s, rng, log)

    print(f"[datagen] writing {ns.certification_pdfs} certification PDFs",
          file=sys.stderr)
    for i, s in enumerate(chosen_t1[: ns.certification_pdfs]):
        cert_name = (s.certifications[0] if s.certifications
                     else "ISO 9001")
        pdf_writer.write_certification_pdf(
            out / "certifications" / f"cert_{s.id}_{i+1}.pdf",
            s, cert_name, rng, log,
        )

    # A couple of compliance filings (prose).
    pdf_writer.write_compliance_filing(
        out / "compliance" / "modern_slavery_statement_2026.pdf",
        "Modern Slavery Statement 2026",
        "Grain Apparel Limited publishes this statement pursuant to the "
        "Modern Slavery Act 2015. During the reporting period we audited "
        "all tier-1 suppliers and 48% of tier-2 suppliers against the SA8000 "
        "framework. Remediation plans are in place for 7 identified issues "
        "across 4 tier-1 facilities.",
        rng, log,
    )

    print(f"[datagen] writing {ns.financials_pdf} financial PDFs and "
          f"{ns.financials_xlsx} financial xlsx", file=sys.stderr)
    for s in chosen_t1[: ns.financials_pdf]:
        pdf_writer.write_supplier_financial_pdf(
            out / "financials" / f"financials_{s.id}.pdf", s, rng, log,
        )
    for s in chosen_t1[: ns.financials_xlsx]:
        excel.write_supplier_financial_statement(
            out / "financials" / f"financials_{s.id}.xlsx", s, rng, log,
        )

    print("[datagen] writing policies (docx)", file=sys.stderr)
    for fname, title, body in POLICY_DOCS:
        docx_writer.write_policy(out / "policies" / fname, title, body)

    print(f"[datagen] writing {ns.correspondence} correspondence docx",
          file=sys.stderr)
    for i, s in enumerate(rng.sample(chosen_t1,
                                      k=min(ns.correspondence, len(chosen_t1)))):
        docx_writer.write_correspondence(
            out / "correspondence" / f"email_{i+1:02d}_{s.id}.docx",
            s, rng, log,
        )

    print(f"[datagen] writing {ns.postmortems} post-mortems", file=sys.stderr)
    for i, s in enumerate(rng.sample(chosen_t1,
                                      k=min(ns.postmortems, len(chosen_t1)))):
        docx_writer.write_postmortem(
            out / "postmortems" / f"postmortem_{i+1:02d}_{s.id}.docx",
            f"Incident Post-Mortem — {s.canonical_name}",
            s, rng, log,
        )

    print("[datagen] writing ERP exports (json/xml)", file=sys.stderr)
    structured.write_suppliers_json(out / "erp" / "suppliers_export.json",
                                     pop, extras, rng, log)
    structured.write_skus_json(out / "erp" / "skus_export.json", pop, log)
    structured.write_plants_xml(out / "erp" / "plants_export.xml", pop, log)
    structured.write_routes_json(out / "erp" / "routes_export.json", pop, log)
    structured.write_components_json(out / "erp" / "components_export.json",
                                      pop, log)

    print(f"[datagen] writing {ns.news_articles} news articles",
          file=sys.stderr)
    news.write_news_articles(out / "news", pop, rng, log,
                              n_articles=ns.news_articles)

    print(f"[datagen] writing {ns.charts} chart PNGs", file=sys.stderr)
    charts.write_charts(out / "charts", pop, rng, log, n_charts=ns.charts)

    # 4. REALISM_LOG.md
    log.write(out / "REALISM_LOG.md")

    dt = time.monotonic() - t0
    print(f"[datagen] done in {dt:,.1f}s. output in {out.resolve()}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
