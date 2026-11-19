"""The Army Painter – Shopify-Shop, öffentliches /products.json.

Erkennung einzelner Farben:
  - Tag beginnt mit 'tap-shop-paints'
  - Titel 'Serie: Name' (z. B. 'Speedpaint Marker: Magic Blue')
  - kein Set/Bundle (SKU 'BNDL…', Set-Wörter im Titel)
SKU 'SM1002P' -> Code 'SM1002' ('P'/'S' hinter den Ziffern sind Verpackungsvarianten).
Lacke und Firnisse (Varnish) werden übersprungen.

EAN: /products.json enthält keinen Barcode, /products/<handle>.js schon (variants[].barcode).
lookup_ean() fragt das je Produkt einzeln ab; sync_shops begrenzt die Anzahl pro Lauf.
"""
from __future__ import annotations

import re

from ..ean import normalize_ean
from .base import Product, Scraper, clean, looks_like_set, strip_size

BASE = "https://www.thearmypainter.com"

# Titelpräfix -> Serienname in den bestehenden Daten
SET_MAP = {
    "warpaints fanatic": "Warpaints Fanatic",
    "warpaints fanatic wash": "Warpaints Fanatic Wash",
    "warpaints fanatic metallic": "Warpaints Fanatic",
    "warpaints air": "Warpaints Air",
    "warpaints air metallic": "Warpaints Air",
    "warpaints": "Warpaints",
    "speedpaint": "Speedpaint Set 2.0",
    "speedpaint 2.0": "Speedpaint Set 2.0",
    "speedpaint marker": "Speedpaint Marker",
    "colour primer": "Warpaints Primer",
    "color primer": "Warpaints Primer",
    "warpaints air metallics": "Warpaints Air Metallics",
    "warpaints air fluorescent": "Warpaints Air Fluorescent",
    "warpaints fanatic effects": "Warpaints Fanatic Effects",
    "warpaints effects": "Warpaints Effects",
    "historical": "Warpaints Historical",
    "warpaints historical": "Warpaints Historical",
    "john blanche masterclass": "John Blanche Masterclass",
    "masterclass": "John Blanche Masterclass",
    "quickshade dip": "Quickshade Dip",
}

# Eigene Serie im Shop, in den Altdaten aber unter einer anderen Serie ohne Code geführt
# -> gleichnamige Farbe ohne Code in diesen Serien ist dieselbe
MATCH_SETS = {
    "Warpaints Air Metallics": ["Warpaints Air"],
    "Warpaints Air Fluorescent": ["Warpaints Air"],
    "Warpaints Fanatic Effects": ["Warpaints Fanatic Wash", "Warpaints Fanatic"],
    "Warpaints Fanatic Wash": ["Warpaints Fanatic"],
}
NON_PAINT = re.compile(r"\b(varnish|thinner|medium|cleaner)\b", re.I)


class ArmyPainterScraper(Scraper):
    brand_slug = "army-painter"

    def fetch(self) -> list[Product]:
        out: list[Product] = []
        page = 1
        while True:
            data = self.get_json(f"{BASE}/products.json", params={"limit": 250, "page": page})
            products = data.get("products", [])
            if not products:
                break
            for p in products:
                prod = self.parse(p)
                if prod:
                    out.append(prod)
            page += 1
        return out

    def parse(self, p: dict) -> Product | None:
        title = clean(p.get("title", ""))
        tags = [t.lower() for t in p.get("tags", [])]
        variants = p.get("variants") or [{}]
        sku = (variants[0].get("sku") or "").strip()
        if not any(t.startswith("tap-shop-paints") for t in tags):
            return None
        if (sku.upper().startswith("BNDL") or looks_like_set(title) or ":" not in title
                or NON_PAINT.search(title)):
            self.skipped.append(f"{sku} {title}")
            return None
        prefix, name = (s.strip() for s in title.split(":", 1))
        name = strip_size(name)
        set_name = SET_MAP.get(prefix.lower())
        if set_name is None:
            set_name = prefix
            self.unmapped.add(prefix)
        code = re.sub(r"(?<=\d)[PS]$", "", sku.upper()) or None
        img = (p.get("images") or [{}])[0].get("src")
        return Product(name=name, set=set_name, code=code,
                       url=f"{BASE}/products/{p['handle']}", image=img,
                       match_sets=MATCH_SETS.get(set_name, []),
                       extra={"sku": sku, "handle": p["handle"]})

    def lookup_ean(self, prod: Product) -> str | None:
        """Barcode der ersten Variante aus /products/<handle>.js."""
        handle = prod.extra.get("handle")
        if not handle:
            return None
        data = self.get_json(f"{BASE}/products/{handle}.js")
        for v in data.get("variants") or []:
            ean = normalize_ean(v.get("barcode"))
            if ean:
                return ean
        return None
