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
    ean: str | None = None
    # Serien, in denen eine gleichnamige Farbe OHNE Code dieselbe ist (Abgleich, wenn der Code nicht trifft)
    match_sets: list[str] = field(default_factory=list)
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
            try:
                r = self.session.get(url, params=params, headers=headers, timeout=30)
            except (requests.ConnectionError, requests.Timeout):
                if attempt == retries - 1:
                    raise
                time.sleep(10 * (attempt + 1))  # Verbindung abgebrochen -> kurz warten, neu versuchen
                continue
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
ACRONYMS = {"osl", "nmm", "afv", "us", "usa", "uk", "ww1", "wwi", "wwii", "raf", "rlm", "ijn", "ija", "dak", "nato", "uv"}


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(text or "")).strip()


def smart_title(text: str) -> str:
    """'MOON MIST GREY' -> 'Moon Mist Grey'; gemischte Schreibweise bleibt unverändert."""
    text = clean(text)
    if text != text.upper():
        return text
    words = text.lower().split(" ")
    return " ".join(w.upper() if w in ACRONYMS else w if (i and w in SMALL_WORDS) else w[:1].upper() + w[1:]
                    for i, w in enumerate(words))


SIZE = re.compile(r"[\s,]*\b\d+(?:[.,]\d+)?\s*ml\b\.?", re.I)


def strip_size(text: str) -> str:
    """'Alien Ooze 10ml' -> 'Alien Ooze'; 'Gloss Varnish, 100 ml' -> 'Gloss Varnish'."""
    return clean(SIZE.sub("", text)).strip(" -,")


SET_WORDS = re.compile(r"\b(set|sets|bundle|triad|triads|case|box|pack|kit|collection|starter|display|expansion|"
                       r"tips|brush|brushes|palette|holder|rack)\b", re.I)


def looks_like_set(title: str) -> bool:
    return bool(SET_WORDS.search(title))
