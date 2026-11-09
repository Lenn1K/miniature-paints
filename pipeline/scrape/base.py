"""Basis für Hersteller-Scraper.

Ein Scraper liefert nur Produkt-Stammdaten (Code, Name, Serie, URL, Bild).
Farbwerte kommen NICHT aus Shops – Shopbilder sind Flaschenfotos, keine Messwerte.
Neue Produkte landen mit status "new" und hex=null in den Daten und im Report.
"""
from __future__ import annotations

import html
import json
import re
import time
from dataclasses import dataclass, field

import requests

from ..lib import USER_AGENT


@dataclass
class Product:
    name: str
    set: str | None
    code: str | None = None
    url: str | None = None
    image: str | None = None
    extra: dict = field(default_factory=dict)


class Scraper:
    brand_slug: str = ""
    delay: float = 1.0  # Sekunden zwischen Requests – höflich bleiben

    def __init__(self):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.skipped: list[str] = []   # bewusst ignorierte Produkte (Sets, Zubehör ...)
        self.unmapped: set[str] = set()  # unbekannte Serien -> Mapping ergänzen

    def get(self, url: str, *, params=None, headers=None, retries: int = 3) -> requests.Response:
        for attempt in range(retries):
            time.sleep(self.delay * (attempt + 1))
            r = self.session.get(url, params=params, headers=headers, timeout=30)
            if r.status_code in (429, 503):
                time.sleep(10 * (attempt + 1))
                continue
            r.raise_for_status()
            return r
        r.raise_for_status()
        return r

    def get_json(self, url: str, **kw):
        return json.loads(self.get(url, **kw).text)

    def fetch(self) -> list[Product]:
        raise NotImplementedError


# ---------- Hilfen für Namen ----------

SMALL_WORDS = {"of", "the", "and", "de", "a", "in", "on"}


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(text or "")).strip()


def smart_title(text: str) -> str:
    """'MOON MIST GREY' -> 'Moon Mist Grey'; gemischte Schreibweise bleibt unverändert."""
    text = clean(text)
    if text != text.upper():
        return text
    words = text.lower().split(" ")
    return " ".join(w if (i and w in SMALL_WORDS) else w[:1].upper() + w[1:] for i, w in enumerate(words))


SET_WORDS = re.compile(r"\b(set|sets|bundle|triad|triads|case|box|pack|kit|collection|starter|display|expansion|"
                       r"tips|brush|brushes|palette|holder|rack)\b", re.I)


def looks_like_set(title: str) -> bool:
    return bool(SET_WORDS.search(title))
