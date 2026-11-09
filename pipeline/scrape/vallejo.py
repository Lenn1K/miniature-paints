"""Acrylicos Vallejo – WooCommerce Store API (/wp-json/wc/store/v1/products).

Liefert englische Namen und die SKU im Format '71.242' direkt (anders als die Sitemap,
deren URLs teils keinen oder einen falschen Code enthalten).
Abgefragt werden nur die Kategorien in CATEGORY_MAP – Sets, Zubehör, Bücher usw. fallen damit raus.
"""
from __future__ import annotations

import re

from .base import Product, Scraper, clean, looks_like_set

BASE = "https://acrylicosvallejo.com"
API = f"{BASE}/wp-json/wc/store/v1/products"

# Kategorie-Slug -> Serienname in den bestehenden Daten
CATEGORY_MAP = {
    "model-color-en": "Model Color",
    "model-air-en": "Model Air",
    "game-color-en": "Game Color",
    "game-air-en": "Game Air",
    "xpress-color-en": "Xpress Color",
    "mecha-color-en": "Mecha Color",
    "metal-color-en": "Metal Color",
    "premium-color-en": "Premium Airbrush Color",
    "primers-en": "Surface Primer",
    "wash-fx-en": "Wash FX",
    "weathering-fx-en": "Weathering FX",
    "hobby-paint": "Hobby Paint",
    "liquid-metal-en": "Liquid Gold",
    "true-metallic-metal-en": "True Metallic Metal",
    "squidmar-color-en": "Squidmar Color",
    # bei Bedarf ergänzen: "pigment-fx-en": "Pigment FX", "diorama-fx-en": "Diorama FX"
}
SKU_RE = re.compile(r"^(\d{2})\.?(\d{3})$")   # '76109' kommt auch vor -> '76.109'
NON_PAINT = re.compile(r"\b(varnish|medium|thinner|cleaner|retarder|flow improver)\b", re.I)


class VallejoScraper(Scraper):
    brand_slug = "vallejo"
    delay = 1.5

    def fetch(self) -> list[Product]:
        out: dict[str, Product] = {}
        seen_names: set[tuple] = set()  # True Metallic Metal: gleiche Farbe in mehreren Größen/SKUs
        for cat, set_name in CATEGORY_MAP.items():
            page = 1
            while True:
                r = self.get(API, params={"category": cat, "per_page": 100, "page": page})
                items = r.json()
                for item in items:
                    p = self.parse(item, set_name)
                    key = (p.set, p.name.lower()) if p else None
                    if p and p.code not in out and key not in seen_names:
                        out[p.code] = p
                        seen_names.add(key)
                if not items or page >= int(r.headers.get("X-WP-TotalPages", page)):
                    break
                page += 1
        return list(out.values())

    def parse(self, item: dict, set_name: str) -> Product | None:
        sku = (item.get("sku") or "").strip()
        name = clean(item.get("name", ""))
        m = SKU_RE.match(sku)
        if not m or looks_like_set(name) or NON_PAINT.search(name):
            self.skipped.append(f"{sku} {name}")
            return None
        sku = f"{m[1]}.{m[2]}"
        img = (item.get("images") or [{}])[0].get("src")
        return Product(name=name, set=set_name, code=sku, url=item.get("permalink"), image=img,
                       extra={"categories": [c.get("slug") for c in item.get("categories", [])]})
