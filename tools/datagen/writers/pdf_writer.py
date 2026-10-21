"""PDF writers: supplier audit reports, contracts, certifications,
compliance filings, per-supplier financial statements.

reportlab lays out prose + embedded tables. OCR-style noise is injected
into some audit reports via the mess module.
"""
from __future__ import annotations

import random
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from tools.datagen.entities import Pop, Supplier
from tools.datagen.mess import ocr_noise, pick_name_variant
from tools.datagen.realism_log import RealismLog

_styles = getSampleStyleSheet()
_H1 = ParagraphStyle("H1", parent=_styles["Heading1"], fontSize=16, spaceAfter=10)
_H2 = ParagraphStyle("H2", parent=_styles["Heading2"], fontSize=12, spaceAfter=6)
_BODY = ParagraphStyle("B", parent=_styles["BodyText"], fontSize=10,
                       leading=14, spaceAfter=6)


def _doc(path: Path, title: str) -> SimpleDocTemplate:
    return SimpleDocTemplate(
        str(path), pagesize=A4,
        rightMargin=18 * mm, leftMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title=title,
    )


def _table(data: list[list[str]], *, header_rows: int = 1) -> Table:
    t = Table(data, repeatRows=header_rows)
    style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, header_rows - 1), colors.lightgrey),
        ("FONTNAME",   (0, 0), (-1, header_rows - 1), "Helvetica-Bold"),
        ("GRID",       (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE",   (0, 0), (-1, -1), 9),
        ("VALIGN",     (0, 0), (-1, -1), "TOP"),
    ])
    t.setStyle(style)
    return t


def write_audit_report(path: Path, s: Supplier, pop: Pop,
                       alt_capacity: str | None,
                       rng: random.Random, log: RealismLog) -> Path:
    """Prose + embedded findings table + a certifications table. ~30% of
    reports get OCR noise applied to the prose section."""
    doc = _doc(path, f"Audit Report - {s.canonical_name}")
    story = []
    name_in_doc = pick_name_variant(rng, s, log, context=f"audit:{s.id}")

    story.append(Paragraph(f"Supplier Audit Report — {name_in_doc}", _H1))
    story.append(Paragraph(
        f"Supplier ID: {s.id} &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"Country: {s.country_name} &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"Audit date: 2026-{rng.randint(1,10):02d}-{rng.randint(1,28):02d}",
        _BODY))

    # Executive summary
    story.append(Paragraph("Executive Summary", _H2))
    cap_text = alt_capacity or f"{s.annual_capacity_units:,}"
    certs_str = (", ".join(s.certifications) if s.certifications
                 else "none at time of audit")
    rating = rng.choice(["Satisfactory", "Needs improvement",
                         "Strong", "Marginal"])
    risk = rng.choice([
        "fire safety on upper floors",
        "electrical compliance in the dyeing unit",
        "subcontracting disclosure",
        "overtime documentation",
        "chemical storage ventilation",
    ])
    exec_para = (
        f"{name_in_doc} operates from {s.city}, {s.country_name} with "
        f"approximately {s.employees:,} employees across its production "
        f"facilities. Stated annual capacity is {cap_text} units. "
        f"Management reported adherence to the following certifications: "
        f"{certs_str}. Overall rating: {rating}. "
        f"Key risks identified relate to {risk}."
    )
    # ~50% receive OCR noise over the exec summary.
    if rng.random() < 0.5:
        exec_para = ocr_noise(exec_para, rng, log,
                              context=f"audit:{s.id}:exec_summary")
    story.append(Paragraph(exec_para, _BODY))

    # Findings table
    story.append(Paragraph("Findings", _H2))
    findings_data = [["#", "Category", "Severity", "Observation", "Status"]]
    for i in range(rng.randint(3, 7)):
        cat = rng.choice(["Fire safety", "Electrical", "Chemical handling",
                          "Child labour screening", "Working hours",
                          "Payroll records", "Subcontracting", "Water discharge"])
        sev = rng.choice(["Minor", "Major", "Critical", "Observation"])
        obs = rng.choice([
            "Second emergency exit obstructed by stored cartons.",
            "Fire extinguisher inspection tags expired 4 months prior.",
            "Chemical SDS not available at point of use for 2 of 5 dyes.",
            "Night-shift payroll records show 7 workers with no NID copy on file.",
            "Weekly OT exceeded the 60-hour limit for 11% of sampled payslips.",
            "ETP log book entries incomplete for Jul-Aug.",
            "Subcontractor list missing one tier-2 fabric mill.",
        ])
        status = rng.choice(["Open", "In progress", "Closed", "CAP agreed"])
        findings_data.append([str(i + 1), cat, sev, obs, status])
    story.append(_table(findings_data))

    story.append(Spacer(1, 6 * mm))

    # Certifications table
    story.append(Paragraph("Certifications on file", _H2))
    cert_data = [["Certification", "Issued", "Expires", "Scope"]]
    for cert in s.certifications or ["(none)"]:
        issued = f"2024-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"
        expires = f"2027-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"
        cert_data.append([cert, issued, expires,
                          rng.choice(["Site-wide", "Production block A",
                                      "Dyeing unit", "Finished garments"])])
    story.append(_table(cert_data))

    doc.build(story)
    return path


def write_contract(path: Path, s: Supplier, rng: random.Random,
                   log: RealismLog) -> Path:
    """Short master supply agreement. Prose heavy; useful for narrative
    track extraction tests."""
    doc = _doc(path, f"Supply Agreement - {s.canonical_name}")
    story = []
    name_in_doc = pick_name_variant(rng, s, log, context=f"contract:{s.id}")
    story.append(Paragraph("MASTER SUPPLY AGREEMENT", _H1))
    story.append(Paragraph(
        f"This Master Supply Agreement (the \"Agreement\") is made as of "
        f"{date(2025, rng.randint(1, 12), rng.randint(1, 28)).isoformat()} "
        f"between <b>GRAIN APPAREL LIMITED</b>, having its registered "
        f"office at 14 Garment Hub, London EC1 (the \"Buyer\"), "
        f"and <b>{name_in_doc.upper()}</b>, having its registered office at "
        f"{s.address} (the \"Supplier\").", _BODY))

    sections = [
        ("1. Scope",
         f"The Supplier shall manufacture and supply apparel products to "
         f"the Buyer in accordance with purchase orders issued under this "
         f"Agreement. The Supplier's tax identification number is {s.tax_id}."),
        ("2. Pricing and currency",
         f"All prices are expressed in United States Dollars (USD). The "
         f"Supplier's reporting currency is {s.primary_currency}. "
         f"Payment terms: net {rng.choice([30, 45, 60])} days from invoice."),
        ("3. Incoterms",
         f"Shipments shall be made on {rng.choice(s.incoterms) if s.incoterms else 'FOB'} "
         f"basis unless specified otherwise on the applicable purchase order."),
        ("4. Audit rights",
         "The Buyer shall have the right, on reasonable notice, to audit "
         "the Supplier's facilities, records, and sub-tier suppliers "
         "including fabric mills, trim suppliers, and dyeing houses."),
        ("5. Subcontracting",
         "The Supplier shall not subcontract any portion of the production "
         "to any facility not previously disclosed to and approved by the "
         "Buyer in writing."),
        ("6. Governing law",
         f"This Agreement shall be governed by the laws of "
         f"{rng.choice(['England and Wales', 'Singapore', 'Hong Kong SAR'])}."),
    ]
    for h, body in sections:
        story.append(Paragraph(h, _H2))
        story.append(Paragraph(body, _BODY))

    doc.build(story)
    return path


def write_certification_pdf(path: Path, s: Supplier, cert_name: str,
                             rng: random.Random, log: RealismLog) -> Path:
    doc = _doc(path, f"{cert_name} - {s.canonical_name}")
    story = [
        Paragraph(f"Certificate of Conformity — {cert_name}", _H1),
        Paragraph(f"Issued to: <b>{s.canonical_name}</b>", _BODY),
        Paragraph(f"Facility address: {s.address}", _BODY),
        Paragraph(f"Scope: Apparel manufacturing. "
                  f"Valid from 2025-01 to 2028-01. "
                  f"Certificate number: {rng.randint(10_000, 999_999)}-{cert_name[:4]}.", _BODY),
    ]
    doc.build(story)
    return path


def write_compliance_filing(path: Path, title: str, body_text: str,
                             rng: random.Random, log: RealismLog) -> Path:
    doc = _doc(path, title)
    story = [Paragraph(title, _H1), Paragraph(body_text, _BODY)]
    doc.build(story)
    return path


def write_supplier_financial_pdf(path: Path, s: Supplier,
                                  rng: random.Random,
                                  log: RealismLog) -> Path:
    """Human-readable financials. Same supplier may also have an .xlsx
    counterpart written by the excel writer; the ingest should correlate."""
    doc = _doc(path, f"Financials - {s.canonical_name}")
    story = []
    story.append(Paragraph(f"Financial Statement FY2026 — {s.canonical_name}", _H1))
    story.append(Paragraph(f"Supplier ID: {s.id}", _BODY))
    story.append(Paragraph(f"Reporting currency: {s.primary_currency}", _BODY))

    revenue = int(s.annual_capacity_units * rng.uniform(0.4, 0.95)
                  * rng.uniform(4, 18))
    cogs = int(revenue * rng.uniform(0.62, 0.82))
    gm = revenue - cogs
    opex = int(revenue * rng.uniform(0.09, 0.18))
    ebit = gm - opex
    tax = max(0, int(ebit * 0.22))
    data = [
        ["Line item", "Amount", "YoY"],
        ["Revenue", f"{revenue:,}", "+6.2%"],
        ["COGS", f"{cogs:,}", "+5.1%"],
        ["Gross margin", f"{gm:,}", "+9.3%"],
        ["Operating expenses", f"{opex:,}", "+4.0%"],
        ["EBIT", f"{ebit:,}", "+14.8%"],
        ["Tax", f"{tax:,}", ""],
        ["Net income", f"{ebit - tax:,}", "+15.1%"],
    ]
    story.append(_table(data))
    doc.build(story)
    return path
