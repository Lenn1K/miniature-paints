"""Acrylicos Vallejo – WooCommerce Store API (/wp-json/wc/store/v1/products).

Liefert englische Namen und die SKU im Format '71.242' direkt (anders als die Sitemap,
deren URLs teils keinen oder einen falschen Code enthalten).
Abgefragt werden nur die Kategorien in CATEGORY_MAP – Sets, Zubehör, Bücher usw. fallen damit raus.

Sprache: Ohne Sprachwahl liefert die API die spanische Hauptsprache (Namen wie „Acero Divino“,
Links unter /producto/). Deshalb werden der englische Pfad (/en/wp-json/…) und ?lang=en
probiert; genommen wird der erste, dessen Links unter /en/ liegen. Klappt keiner, bricht der
Lauf ab, statt spanische Namen einzutragen. Einzelne Produkte ohne englischen Link werden
übersprungen und im Bericht genannt.

EAN: Vallejo-EANs sind 8429551 + Artikelnummer ohne Punkt + Prüfziffer (siehe pipeline/ean.py).
"""
from __future__ import annotations

import re

from ..ean import vallejo_ean
from .base import Product, Scraper, clean, looks_like_set

BASE = "https://acrylicosvallejo.com"
API = f"{BASE}/wp-json/wc/store/v1/products"
# (URL, Parameter) in dieser Reihenfolge probieren
API_CANDIDATES = [
    (f"{BASE}/en/wp-json/wc/store/v1/products", {}),
    (API, {"lang": "en"}),
    (f"{BASE}/en/wp-json/wc/store/v1/products", {"lang": "en"}),
]

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

    def pick_api(self) -> tuple[str, dict]:
        """Erste API-Variante, die englische Produkte liefert."""
        cat = next(iter(CATEGORY_MAP))
        tried = []
        for url, extra in API_CANDIDATES:
            try:
                items = self.get(url, params={**extra, "category": cat, "per_page": 20}).json()
            except Exception as e:  # 404 o. Ä. -> nächste Variante
                tried.append(f"{url} {extra}: {type(e).__name__}")
                continue
            links = [i.get("permalink", "") for i in items if isinstance(i, dict)]
            if links and sum(is_english(l) for l in links) * 2 > len(links):
                return url, extra
            tried.append(f"{url} {extra}: keine englischen Links ({links[:1]})")
        raise RuntimeError("Store API liefert keine englischen Produkte – " + "; ".join(tried))

    def fetch(self) -> list[Product]:
        out: dict[str, Product] = {}
        seen_names: set[tuple] = set()  # True Metallic Metal: gleiche Farbe in mehreren Größen/SKUs
        api, extra = self.pick_api()
        for cat, set_name in CATEGORY_MAP.items():
            page = 1
            while True:
                r = self.get(api, params={**extra, "category": cat, "per_page": 100, "page": page})
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
        link = item.get("permalink") or ""
        if not is_english(link):
            self.unmapped.add(f"nicht englisch: {sku} {name} {link}")
            return None
        m = SKU_RE.match(sku)
        if not m or looks_like_set(name) or NON_PAINT.search(name):
            self.skipped.append(f"{sku} {name}")
            return None
        sku = f"{m[1]}.{m[2]}"
        img = (item.get("images") or [{}])[0].get("src")
        return Product(name=name, set=set_name, code=sku, url=link, image=img, ean=vallejo_ean(sku),
                       extra={"categories": [c.get("slug") for c in item.get("categories", [])]})


def is_english(link: str) -> bool:
    return "/en/" in link
