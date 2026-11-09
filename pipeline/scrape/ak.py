"""AK Interactive – WooCommerce Store API (/wp-json/wc/store/v1/products).

Der Shop liefert jedes Produkt zweisprachig (ES unter /es/, EN ohne Präfix); wir nehmen EN.
Abgefragt wird die Kategorie '3GEN ACRYLICS' (slug 3rd-acrylics) – weitere Kategorien
über CATEGORIES ergänzen.

Name:  'WHITE – INTENSE'  ->  Name 'White', Unterserie 'Intense' -> Set 'Intense (3rd Gen)'
"""
from __future__ import annotations

import re

from .base import Product, Scraper, clean, looks_like_set, smart_title

BASE = "https://ak-interactive.com"
API = f"{BASE}/wp-json/wc/store/v1/products"

# Kategorie-Slug -> Suffix für den Seriennamen
CATEGORIES = {
    "3rd-acrylics": " (3rd Gen)",
}

# Unterkategorien (EN), die als Serie taugen -> Serienname in den bestehenden Daten
SUBRANGES = {
    "standard": "Standard", "intense": "Intense", "metallic": "Metallic", "pastel": "Pastel",
    "primer": "Primer", "primers": "Primer", "ink": "Ink", "inks": "Ink", "auxiliary": "Auxiliary",
    "auxiliaries": "Auxiliary", "figures": "Figures", "afv": "AFV", "air": "Air",
    "afv serie": "AFV", "air serie": "Air", "figures serie": "Figures",
    "3gen color punch": "Color Punch", "color punch": "Color Punch",
}


class AKScraper(Scraper):
    brand_slug = "ak"

    def fetch(self) -> list[Product]:
        out: dict[str, Product] = {}
        for cat, suffix in CATEGORIES.items():
            page = 1
            while True:
                r = self.get(API, params={"category": cat, "per_page": 100, "page": page})
                items = r.json()
                for item in items:
                    prod = self.parse(item, suffix)
                    if prod and prod.code not in out:
                        out[prod.code] = prod
                total_pages = int(r.headers.get("X-WP-TotalPages", page))
                if not items or page >= total_pages:
                    break
                page += 1
        return list(out.values())

    def parse(self, item: dict, suffix: str) -> Product | None:
        link = item.get("permalink", "")
        if "/es/" in link:          # spanische Dublette
            return None
        sku = (item.get("sku") or "").strip().upper()
        title = clean(item.get("name", ""))
        cat_text = " ".join(f"{c.get('name', '')} {c.get('slug', '')}" for c in item.get("categories", [])).lower()
        if (not re.fullmatch(r"AK\d{3,6}", sku) or looks_like_set(title) or "set" in cat_text.split()
                or re.search(r"\bsets?\b|briefcase|malet", cat_text + " " + title.lower())):
            self.skipped.append(f"{sku} {title}")
            return None
        parts = [p.strip() for p in re.split(r"\s+[–-]\s+", title) if p.strip()]
        name = smart_title(parts[0])
        sub = None
        for c in item.get("categories", []):
            key = clean(c.get("name", "")).lower()
            if key in SUBRANGES:
                sub = SUBRANGES[key]
                break
        if sub is None and len(parts) > 1 and parts[1].lower() in SUBRANGES:
            sub = SUBRANGES[parts[1].lower()]
        if sub is None:  # lieber auslassen und im Report melden als falsch einsortieren
            self.unmapped.add(f"{sku} {title} – " + " / ".join(clean(c.get("name", "")) for c in item.get("categories", [])))
            return None
        img = (item.get("images") or [{}])[0].get("src")
        return Product(name=name, set=f"{sub}{suffix}", code=sku, url=link, image=img,
                       extra={"title": title})
