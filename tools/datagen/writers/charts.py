"""Chart screenshots as PNGs for vision-extraction tests.

Deliberately simple — bar charts drawn with Pillow (which comes in as a
reportlab transitive dep). The point is to give the ingest pipeline a
handful of image files it has to decide what to do with, not to produce
publication-grade figures.
"""
from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from tools.datagen.entities import Pop
from tools.datagen.realism_log import RealismLog

_W, _H = 900, 500
_MARGIN = 60


def _font(size: int = 14) -> ImageFont.ImageFont:
    # DejaVu is usually available on Linux. Fall back to default silently.
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size=size)
    except OSError:
        return ImageFont.load_default()


def _draw_bar_chart(path: Path, title: str, labels: list[str],
                    values: list[float], y_label: str) -> Path:
    img = Image.new("RGB", (_W, _H), "white")
    d = ImageDraw.Draw(img)
    d.text((_MARGIN, 15), title, fill="black", font=_font(18))
    d.text((_MARGIN, 40), y_label, fill="#555", font=_font(12))
    chart_top = 80
    chart_bottom = _H - 60
    chart_left = _MARGIN
    chart_right = _W - _MARGIN
    # Axes
    d.line([(chart_left, chart_top), (chart_left, chart_bottom)], fill="black", width=2)
    d.line([(chart_left, chart_bottom), (chart_right, chart_bottom)], fill="black", width=2)
    # Bars
    n = len(values)
    if n == 0:
        img.save(path)
        return path
    max_v = max(values) or 1.0
    span = chart_right - chart_left - 20
    bar_w = span / n * 0.7
    gap = span / n * 0.3
    x = chart_left + 10
    for lbl, v in zip(labels, values, strict=False):
        h = (v / max_v) * (chart_bottom - chart_top - 20)
        y_top = chart_bottom - h
        d.rectangle([x, y_top, x + bar_w, chart_bottom], fill="#5e81ac", outline="black")
        d.text((x, chart_bottom + 6), lbl, fill="black", font=_font(10))
        d.text((x, y_top - 14), f"{v:,.0f}", fill="black", font=_font(10))
        x += bar_w + gap
    img.save(path)
    return path


def write_charts(dir_path: Path, pop: Pop, rng: random.Random,
                  log: RealismLog, *, n_charts: int = 8) -> list[Path]:
    dir_path.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    # 1. Top-10 suppliers by capacity
    top = sorted(pop.suppliers, key=lambda s: -s.annual_capacity_units)[:10]
    out.append(_draw_bar_chart(
        dir_path / "chart_01_top10_capacity.png",
        "Top-10 suppliers by stated annual capacity (units)",
        [s.canonical_name.split(" ")[0][:10] for s in top],
        [s.annual_capacity_units for s in top],
        "Units per year",
    ))
    # 2. Lead-time distribution (synthetic buckets)
    buckets = ["<30", "30-45", "45-60", "60-75", "75-90", "90+"]
    vals = [rng.randint(20, 180) for _ in buckets]
    out.append(_draw_bar_chart(
        dir_path / "chart_02_leadtime_hist.png",
        "Tier-1 average lead time distribution (days)",
        buckets, vals, "Count of suppliers",
    ))
    # 3. Country concentration
    by_country: dict[str, int] = {}
    for s in pop.suppliers:
        by_country[s.country_name] = by_country.get(s.country_name, 0) + 1
    top_c = sorted(by_country.items(), key=lambda kv: -kv[1])[:8]
    out.append(_draw_bar_chart(
        dir_path / "chart_03_country_concentration.png",
        "Supplier count by country",
        [c for c, _ in top_c], [v for _, v in top_c],
        "Number of suppliers",
    ))
    # 4..N: fill with slightly perturbed capacity charts for variety
    for i in range(4, n_charts + 1):
        sample = rng.sample(pop.suppliers, k=min(8, len(pop.suppliers)))
        out.append(_draw_bar_chart(
            dir_path / f"chart_{i:02d}_capacity_sample.png",
            f"Capacity sample #{i-3}",
            [s.canonical_name.split(' ')[0][:10] for s in sample],
            [s.annual_capacity_units for s in sample],
            "Units per year",
        ))
    log.bump("charts.images_written", len(out))
    return out
