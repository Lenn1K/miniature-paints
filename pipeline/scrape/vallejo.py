"""Acrylicos Vallejo – WordPress-Seite, Produkte über die XML-Sitemap entdecken.

Produkt-URLs: /en/product/hobby/<serie>/<name-slug>-<code>/
  z. B. /en/product/hobby/model-color/white-70951/  ->  Model Color, 70.951, 'White'
Für NEUE Produkte wird zusätzlich die Produktseite geladen, um den exakten Namen (og:title/h1)
zu bekommen – bekannte Produkte kosten keinen zusätzlichen Request.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup

from .base import Product, Scraper, clean, looks_like_set

BASE = "https://acrylicosvallejo.com"
SITEMAP_CANDIDATES = [f"{BASE}/sitemap_index.xml", f"{BASE}/wp-sitemap.xml", f"{BASE}/sitemap.xml"]
PRODUCT_RE = re.compile(r"/en/product/hobby/(?P<range>[a-z0-9-]+)/(?P<slug>[a-z0-9-]+?)-(?P<code>\d{5})/?$")

# URL-Serie -> Serienname in den bestehenden Daten (None = ignorieren)
RANGE_MAP = {
    "model-color": "Model Color",
    "model-air": "Model Air",
    "game-color": "Game Color",
    "game-air": "Game Air",
    "xpress-color": "Xpress Color",
    "mecha-color": "Mecha Color",
    "metal-color": "Metal Color",
    "panzer-aces": "Panzer Aces",
    "surface-primer": "Surface Primer",
    "premium-airbrush-color": "Premium Airbrush Color",
    "premium-color": "Premium Airbrush Color",
    "hobby-paint": "Hobby Paint",
    "weathering-fx": "Weathering FX",
    "wash-fx": "Wash FX",
    "true-metallic-metal": "True Metallic Metal",
    "liquid-gold": "Liquid Gold",
    "brushes": None, "airbrushes": None, "tools": None, "auxiliaries": None,
    "diorama-fx": None, "pigments": None, "varnishes-and-mediums": None,
}
NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def code_from_digits(d: str) -> str:
    return f"{d[:2]}.{d[2:]}"


class VallejoScraper(Scraper):
    brand_slug = "vallejo"
    delay = 2.0

    def sitemap_urls(self) -> list[str]:
        for idx in SITEMAP_CANDIDATES:
            try:
                root = ET.fromstring(self.get(idx).content)
            except Exception:
                continue
            locs = [e.text for e in root.findall(".//sm:loc", NS)]
            if root.tag.endswith("sitemapindex"):
                urls = []
                for sm in locs:
                    if "product" in sm:
                        sub = ET.fromstring(self.get(sm).content)
                        urls += [e.text for e in sub.findall(".//sm:loc", NS)]
                return urls
            return locs
        raise RuntimeError("Keine Vallejo-Sitemap gefunden – SITEMAP_CANDIDATES prüfen")

    def fetch(self) -> list[Product]:
        out: dict[str, Product] = {}
        for url in self.sitemap_urls():
            m = PRODUCT_RE.search(url or "")
            if not m:
                continue
            rng, slug, digits = m["range"], m["slug"], m["code"]
            if rng not in RANGE_MAP:
                self.unmapped.add(rng)
                set_name = rng.replace("-", " ").title()
            else:
                set_name = RANGE_MAP[rng]
                if set_name is None:
                    continue
            if looks_like_set(slug.replace("-", " ")):
                self.skipped.append(url)
                continue
            code = code_from_digits(digits)
            out.setdefault(code, Product(name=slug.replace("-", " ").title(), set=set_name,
                                         code=code, url=url, extra={"name_from_slug": True}))
        return list(out.values())

    def enrich(self, p: Product) -> Product:
        """Exakter Name + Bild von der Produktseite (nur für neue Produkte aufgerufen)."""
        soup = BeautifulSoup(self.get(p.url).text, "html.parser")
        og = soup.find("meta", property="og:title")
        h1 = soup.find("h1")
        title = clean(og["content"] if og and og.get("content") else (h1.get_text() if h1 else ""))
        title = re.sub(r"\s*[-|–].*?Vallejo.*$", "", title, flags=re.I)   # ' - Acrylicos Vallejo'
        title = re.sub(r"\s*\d{2}\.?\d{3}\s*$", "", title).strip()         # Code am Ende
        if title:
            p.name = title
            p.extra.pop("name_from_slug", None)
        img = soup.find("meta", property="og:image")
        if img and img.get("content"):
            p.image = img["content"]
        return p
