"""Gemeinsame Hilfsfunktionen: Laden/Speichern der Markendaten, IDs, Farbumrechnung."""
from __future__ import annotations

import json
import math
import re
import unicodedata
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
BRANDS_DIR = DATA_DIR / "brands"
REPORTS_DIR = ROOT / "reports"
DIST_DIR = ROOT / "dist"

TODAY = date.today().isoformat()

# Feldreihenfolge in den JSON-Dateien (stabile Diffs). RGB wird nicht gespeichert,
# sondern beim Build aus hex abgeleitet – eine Quelle, keine Inkonsistenzen.
FIELD_ORDER = [
    "id", "name", "code", "set", "hex", "status",
    "names", "url", "image", "color_source", "alt_colors",
    "nearest_color_name", "first_seen", "last_seen",
]


# ---------- Strings / IDs ----------

def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or "x"


def norm_code(code: str | None) -> str | None:
    """Vergleichsform eines Herstellercodes: '70.951' == '70951' == 'VAL-70951'?

    Entfernt Punkte, Leerzeichen, Bindestriche und macht Großbuchstaben.
    Präfixe wie 'VAL-' werden NICHT entfernt – das macht der jeweilige Scraper.
    """
    if not code or code.lower() == "null":
        return None
    return re.sub(r"[\s.\-_/]", "", code).upper()


def norm_name(name: str) -> str:
    return slugify(name)


def make_id(brand_slug: str, paint: dict) -> str:
    if paint.get("code"):
        return f"{brand_slug}/{slugify(paint['code'])}"
    return f"{brand_slug}/{slugify(paint.get('set') or 'none')}--{slugify(paint['name'])}"


# ---------- Farbe ----------

def hex_to_rgb(h: str) -> list[int]:
    h = h.lstrip("#")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def rgb_to_hex(rgb) -> str:
    return "#" + "".join(f"{int(c):02X}" for c in rgb)


def _srgb_to_linear(c: float) -> float:
    c /= 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def rgb_to_lab(rgb) -> tuple[float, float, float]:
    r, g, b = (_srgb_to_linear(c) for c in rgb)
    x = (r * 0.4124564 + g * 0.3575761 + b * 0.1804375) / 0.95047
    y = (r * 0.2126729 + g * 0.7151522 + b * 0.0721750) / 1.00000
    z = (r * 0.0193339 + g * 0.1191920 + b * 0.9503041) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 216 / 24389 else (24389 / 27 * t + 16) / 116

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def delta_e2000(lab1, lab2) -> float:
    """CIEDE2000 – wahrnehmungsnaher Farbabstand."""
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2
    C1, C2 = math.hypot(a1, b1), math.hypot(a2, b2)
    Cm = (C1 + C2) / 2
    G = 0.5 * (1 - math.sqrt(Cm ** 7 / (Cm ** 7 + 25 ** 7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360
    h2p = math.degrees(math.atan2(b2, a2p)) % 360
    dLp = L2 - L1
    dCp = C2p - C1p
    if C1p * C2p == 0:
        dhp = 0.0
    elif abs(h2p - h1p) <= 180:
        dhp = h2p - h1p
    elif h2p - h1p > 180:
        dhp = h2p - h1p - 360
    else:
        dhp = h2p - h1p + 360
    dHp = 2 * math.sqrt(C1p * C2p) * math.sin(math.radians(dhp / 2))
    Lpm = (L1 + L2) / 2
    Cpm = (C1p + C2p) / 2
    if C1p * C2p == 0:
        hpm = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hpm = (h1p + h2p) / 2
    elif h1p + h2p < 360:
        hpm = (h1p + h2p + 360) / 2
    else:
        hpm = (h1p + h2p - 360) / 2
    T = (1 - 0.17 * math.cos(math.radians(hpm - 30)) + 0.24 * math.cos(math.radians(2 * hpm))
         + 0.32 * math.cos(math.radians(3 * hpm + 6)) - 0.20 * math.cos(math.radians(4 * hpm - 63)))
    dtheta = 30 * math.exp(-(((hpm - 275) / 25) ** 2))
    Rc = 2 * math.sqrt(Cpm ** 7 / (Cpm ** 7 + 25 ** 7))
    Sl = 1 + (0.015 * (Lpm - 50) ** 2) / math.sqrt(20 + (Lpm - 50) ** 2)
    Sc = 1 + 0.045 * Cpm
    Sh = 1 + 0.015 * Cpm * T
    Rt = -math.sin(math.radians(2 * dtheta)) * Rc
    return math.sqrt((dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dHp / Sh) ** 2
                     + Rt * (dCp / Sc) * (dHp / Sh))


# ---------- Laden / Speichern ----------

REQUIRED = ("id", "name", "code", "set", "hex", "status")


def ordered(paint: dict) -> dict:
    """Feste Feldreihenfolge; leere optionale Felder entfallen, Pflichtfelder bleiben (ggf. null)."""
    out = {}
    for k in FIELD_ORDER:
        v = paint.get(k)
        if k in REQUIRED or v not in (None, [], {}):
            out[k] = v
    for k, v in paint.items():
        if k not in out and v not in (None, [], {}):
            out[k] = v
    return out


def load_brand(slug: str) -> dict:
    return json.loads((BRANDS_DIR / f"{slug}.json").read_text(encoding="utf-8"))


def save_brand(brand: dict) -> None:
    # Stabile Sortierung nur nach Name: bei Namensgleichheit bleibt die bisherige Reihenfolge erhalten
    brand["paints"] = sorted((ordered(p) for p in brand["paints"]), key=lambda p: p["name"])
    BRANDS_DIR.mkdir(parents=True, exist_ok=True)
    path = BRANDS_DIR / f"{brand['slug']}.json"
    path.write_text(json.dumps(brand, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def all_brand_slugs() -> list[str]:
    return sorted(p.stem for p in BRANDS_DIR.glob("*.json"))


def unique_id(existing: set[str], wanted: str) -> str:
    if wanted not in existing:
        return wanted
    i = 2
    while f"{wanted}~{i}" in existing:
        i += 1
    return f"{wanted}~{i}"


# ---------- HTTP ----------

USER_AGENT = "miniature-paints-sync/1.0 (+https://github.com/Lenn1K/miniature-paints)"


def http_get(url: str, *, timeout: int = 30, accept: str | None = None) -> bytes:
    import urllib.request
    headers = {"User-Agent": USER_AGENT}
    if accept:
        headers["Accept"] = accept
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def read_source(path_or_url: str) -> str:
    """Lokale Datei oder URL lesen (für Tests/Offline-Läufe Pfad übergeben)."""
    if path_or_url.startswith(("http://", "https://")):
        return http_get(path_or_url).decode("utf-8")
    return Path(path_or_url).read_text(encoding="utf-8")


def write_report(name: str, lines: list[str]) -> Path:
    REPORTS_DIR.mkdir(exist_ok=True)
    path = REPORTS_DIR / f"{name}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
