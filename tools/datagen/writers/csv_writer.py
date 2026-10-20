"""CSV writers: shipment log, lead-time history, daily demand time series."""
from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

from tools.datagen.entities import Pop
from tools.datagen.mess import mixed_units_price
from tools.datagen.realism_log import RealismLog


def write_shipment_log(path: Path, pop: Pop, rng: random.Random,
                       log: RealismLog, *, n_rows: int = 8000) -> Path:
    plant_by_id = {p.id: p for p in pop.plants}
    sku_sample = pop.skus
    routes = pop.routes

    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "shipment_id", "shipped_on", "arrived_on", "sku_id",
            "qty_units", "weight_kg", "weight_lb", "origin_plant",
            "origin_port", "dest_port", "route_id", "carrier",
            "incoterm", "invoice_amount", "invoice_currency",
        ])
        for i in range(n_rows):
            sku = rng.choice(sku_sample)
            plant = plant_by_id.get(sku.plant_id)
            route = rng.choice(routes)
            shipped = date(2025, 10, 1) + timedelta(days=rng.randint(0, 360))
            arrived = shipped + timedelta(days=route.transit_days
                                          + rng.randint(-2, 5))
            qty = rng.randint(100, 12_000)
            kg = round(qty * rng.uniform(0.08, 0.6), 1)
            lb = round(kg * 2.20462, 1)
            # Mixed units: in ~10% of rows blank the kg column so the reader
            # has to use lb.
            if rng.random() < 0.1:
                kg_out: float | None = None
                log.bump("units.mixed_weight_only_lb")
            else:
                kg_out = kg
            invoice = round(sku.cost_target_usd * qty, 2)
            # Occasionally invoice is in local currency without a clear label.
            s = next((x for x in pop.suppliers if x.id == sku.tier1_supplier_id), None)
            ccy = s.primary_currency if s else "USD"
            inv_val, inv_ccy = mixed_units_price(rng, invoice, ccy, log,
                                                  context=f"shipment_log row {i}")
            w.writerow([
                f"SHP-{i+1:07d}", shipped.isoformat(), arrived.isoformat(),
                sku.id, qty, kg_out, lb,
                plant.id if plant else "", route.origin_port,
                route.dest_port, route.id, route.carrier,
                rng.choice(["FOB", "CIF", "DDP"]),
                inv_val, inv_ccy,
            ])
    return path


def write_lead_time_history(path: Path, pop: Pop, rng: random.Random,
                             log: RealismLog, *, n_months: int = 18) -> Path:
    tier1 = [s for s in pop.suppliers if s.tier == 1]
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["month", "supplier_id", "sku_count",
                    "avg_lead_time_days", "p95_lead_time_days",
                    "on_time_delivery_pct"])
        start = date(2025, 4, 1)
        for m in range(n_months):
            # Advance month by month.
            yy = start.year + (start.month - 1 + m) // 12
            mm = (start.month - 1 + m) % 12 + 1
            label = f"{yy}-{mm:02d}"
            for s in tier1:
                avg = rng.randint(28, 95)
                p95 = avg + rng.randint(5, 35)
                otd = round(rng.uniform(0.65, 0.98), 3)
                sku_count = rng.randint(1, 40)
                w.writerow([label, s.id, sku_count, avg, p95, otd])
    return path


def write_daily_demand(dir_path: Path, pop: Pop, rng: random.Random,
                        log: RealismLog) -> list[Path]:
    """One CSV per month, mimicking an ERP's monthly rollout dumps."""
    dir_path.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    # Keep each file to top-N SKUs so file size stays reasonable.
    top_skus = pop.skus[: min(300, len(pop.skus))]
    start = date(2025, 10, 1)
    for m in range(12):
        yy = start.year + (start.month - 1 + m) // 12
        mm = (start.month - 1 + m) % 12 + 1
        p = dir_path / f"daily_demand_{yy}-{mm:02d}.csv"
        with p.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["date", "sku_id", "channel", "units_sold"])
            # Days in this month, roughly.
            days = 31 if mm in {1,3,5,7,8,10,12} else (30 if mm != 2 else 28)
            for d in range(1, days + 1):
                day = date(yy, mm, d).isoformat()
                for sku in rng.sample(top_skus, k=min(80, len(top_skus))):
                    for channel in ("retail", "ecom", "wholesale"):
                        base = rng.randint(0, 60)
                        # ecom and retail have different weekday patterns
                        w.writerow([day, sku.id, channel, base])
        out.append(p)
    return out
