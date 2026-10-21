"""News corpus: disruption articles naming real-sounding entities.

Mix of .md and .txt so routing has to handle both. Articles reference
suppliers, plants, ports, and routes using mostly canonical names but
occasionally a variant.
"""
from __future__ import annotations

import random
from datetime import date
from pathlib import Path

from tools.datagen.entities import Pop
from tools.datagen.mess import pick_name_variant
from tools.datagen.realism_log import RealismLog

_HEADLINES = {
    "flood": [
        "{region} flooding disrupts garment shipments at {port}",
        "Monsoon floods strand containers bound for {dest_port}",
    ],
    "fire": [
        "Fire at {supplier} dyeing unit halts production",
        "Blaze reported at {supplier} facility in {city}",
    ],
    "strike": [
        "Dockworkers at {port} begin 72-hour strike over wage demands",
        "Garment-sector strike spreads to {region} industrial zone",
    ],
    "customs": [
        "{dest_country} customs tightens inspections on {origin_country}-origin apparel",
        "New import duty on man-made fibres hits {origin_country} exporters",
    ],
    "quality": [
        "Buyer rejects shipment from {supplier} over dye bleeding issue",
        "{supplier} recalls batch over GOTS compliance query",
    ],
    "esg": [
        "NGO flags labour-hour concerns at {supplier}",
        "{supplier} publishes ESG update after audit findings",
    ],
}


def write_news_articles(dir_path: Path, pop: Pop, rng: random.Random,
                         log: RealismLog, *, n_articles: int = 30) -> list[Path]:
    dir_path.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    categories = list(_HEADLINES.keys())
    for i in range(n_articles):
        cat = rng.choice(categories)
        s = rng.choice(pop.suppliers)
        route = rng.choice(pop.routes)
        name_in_doc = pick_name_variant(rng, s, log, context=f"news:{i}")
        headline_tpl = rng.choice(_HEADLINES[cat])
        headline = headline_tpl.format(
            region=s.country_name,
            port=route.origin_port,
            dest_port=route.dest_port,
            dest_country=route.dest_country,
            origin_country=s.country_name,
            supplier=name_in_doc,
            city=s.city,
        )
        article_date = date(2026, rng.randint(1, 10),
                            rng.randint(1, 28))
        body_paras = _article_body(cat, name_in_doc, s, route, article_date, rng)
        ext = ".md" if rng.random() < 0.6 else ".txt"
        p = dir_path / f"news_{i+1:03d}_{cat}{ext}"
        if ext == ".md":
            lines = [f"# {headline}", "",
                     f"*{article_date.isoformat()} — Trade Press Daily*", "",
                     *body_paras]
        else:
            lines = [headline.upper(),
                     f"{article_date.isoformat()} - Trade Press Daily",
                     "", *body_paras]
        p.write_text("\n\n".join(lines))
        out.append(p)
        log.event("news.article_written",
                  f"{p.name}: category={cat}, references supplier {s.id}, "
                  f"route {route.id}")
    return out


def _article_body(cat: str, name: str, s, route, dt: date,
                   rng: random.Random) -> list[str]:
    base = {
        "flood": [
            f"Heavy monsoon rainfall across {s.country_name} has disrupted overland "
            f"transport to {route.origin_port}, where several containers destined for "
            f"{route.dest_port} remain stranded. Industry sources estimate a 7-10 day "
            f"delay for apparel shipments.",
            f"{name} confirmed that two of its production lines had been idled "
            f"while the roadway near its {s.city} facility was closed.",
        ],
        "fire": [
            f"A fire broke out early {dt.isoformat()} at the dyeing unit operated by "
            f"{name} in {s.city}. No injuries were reported but production is halted "
            f"pending inspection.",
            "The affected unit supplies woven fabric used in several buyers' "
            "autumn 2026 outerwear ranges.",
        ],
        "strike": [
            f"Dockworkers at {route.origin_port} began a 72-hour strike today, "
            f"citing stalled wage negotiations. Carriers including {route.carrier} "
            f"have issued delay notices.",
            f"Apparel exporters warn of knock-on effects for {route.dest_port}-bound "
            f"vessels scheduled this week.",
        ],
        "customs": [
            f"Authorities in {route.dest_country} have introduced tightened inspection "
            f"procedures for apparel of {s.country_name} origin. Clearance times at "
            f"{route.dest_port} have doubled in the past week.",
            "Importers are advised to allow additional buffer in planning cycles.",
        ],
        "quality": [
            f"A European buyer has returned a shipment from {name} citing dye-bleed "
            f"in wash tests. The supplier states it is investigating with its tier-2 "
            f"dyeing partner.",
        ],
        "esg": [
            f"A regional labour-rights NGO has published a report naming {name} among "
            f"five apparel suppliers in {s.country_name} with recurring overtime "
            f"documentation issues.",
            f"{name} said it welcomes the dialogue and will publish its own ESG update.",
        ],
    }
    return base[cat] + [
        "Reporting by Trade Press Daily. This article contains data points from "
        "primary and secondary sources and should be verified by procurement teams "
        "before operational action."
    ]
