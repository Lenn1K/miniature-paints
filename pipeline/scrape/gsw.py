"""Green Stuff World – PrestaShop.

Kategorie '118-model-paints' enthält alle Farben (paginiert über ?page=N).
PrestaShop liefert Kategorieseiten als JSON, wenn man sie per XHR anfragt
(Header 'X-Requested-With: XMLHttpRequest' + Accept JSON); Fallback: HTML parsen.

GSW hat keine Farbcodes im klassischen Sinn – Abgleich über Name + Serie.
Die Referenz (EAN + 'ES') wird als extra.reference mitgeführt.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .base import Product, Scraper, clean, looks_like_set, smart_title

BASE = "https://www.greenstuffworld.com"
CATEGORY = f"{BASE}/en/118-model-paints"

# Titelmuster -> (Serie, Regex mit Gruppe 'name')
TITLE_RULES = [
    ("Acrylic Colors", r"^Acrylic Colou?r\s+(?P<name>.+)$"),
    ("Dipping Inks", r"^Dipping ink(?:\s+\d+\s*ml)?\s*-\s*(?P<name>.+)$"),
    ("Wash Ink", r"^Wash Ink\s*-?\s*(?P<name>.+)$"),
    ("Intensity Ink", r"^Intensity Ink\s*-?\s*(?P<name>.+)$"),
    ("Candy Ink Metallic", r"^Candy Ink\s*-?\s*(?P<name>.+)$"),
    ("Chameleon Colorshift Metallic", r"^Colorshift (?:Chameleon )?(?:Paint|Metallic)?\s*-?\s*(?P<name>.+)$"),
    ("Chameleon Colorshift Metallic", r"^Chameleon\s+(?P<name>.+)$"),
    ("Fluor Metallic", r"^Fluor(?:escent)? (?:Metallic|Paint)?\s*-?\s*(?P<name>.+)$"),
    ("Metallic Colors", r"^Metallic (?:Paint|Colou?r)\s*-?\s*(?P<name>.+)$"),
    ("Opaque Colors", r"^Opaque Colou?rs?\s*-?\s*(?P<name>.+)$"),
    ("Acrylic Inks", r"^Acrylic Ink\s*-?\s*(?P<name>.+)$"),
    ("Matt Surface", r"^(?P<name>.+?)\s*-?\s*Matt(?:e)? Surface(?: Primer)?$"),
]
IGNORE = re.compile(r"\b(thinner|varnish|medium|cleaner|primer spray|glue|empty|bottle|caps?|"
                    r"retarder|mixing balls?|effect|texture|blood|vomit|bile)\b", re.I)


class GreenStuffWorldScraper(Scraper):
    brand_slug = "greenstuffworld"
    delay = 2.0

    def fetch(self) -> list[Product]:
        out: dict[tuple, Product] = {}
        page = 1
        while True:
            items, pages = self.fetch_page(page)
            for title, url, ref, img in items:
                p = self.parse(title, url, ref, img)
                if p:
                    out.setdefault((p.set, p.name.lower()), p)
            if not items or page >= pages:
                break
            page += 1
        return list(out.values())

    def fetch_page(self, page: int):
        r = self.get(CATEGORY, params={"page": page}, headers={
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest"})
        if r.headers.get("Content-Type", "").startswith("application/json"):
            data = r.json()
            items = [(p.get("name", ""), p.get("url"), p.get("reference"),
                      ((p.get("cover") or {}).get("large") or {}).get("url"))
                     for p in data.get("products", [])]
            pages = (data.get("pagination") or {}).get("pages_count", page)
            return items, int(pages)
        # HTML-Fallback (Classic-Theme-Selektoren)
        soup = BeautifulSoup(r.text, "html.parser")
        items = []
        for art in soup.select("article.product-miniature, .product-miniature"):
            a = art.select_one(".product-title a, h2 a, h3 a")
            if not a:
                continue
            img = art.select_one("img")
            items.append((a.get_text(), a.get("href"), None, img.get("src") if img else None))
        nums = [int(x.get_text()) for x in soup.select(".pagination a, .page-list a") if x.get_text().strip().isdigit()]
        return items, max(nums or [page])

    def parse(self, title: str, url: str | None, ref: str | None, img: str | None) -> Product | None:
        title = clean(title)
        if looks_like_set(title) or IGNORE.search(title):
            self.skipped.append(title)
            return None
        for set_name, rx in TITLE_RULES:
            m = re.match(rx, title, re.I)
            if m:
                return Product(name=smart_title(m["name"]), set=set_name, code=None, url=url,
                               image=img, extra={"reference": ref, "title": title})
        self.unmapped.add(title)
        return None
