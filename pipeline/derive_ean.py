"""EANs herleiten, wo sie sich aus dem Herstellercode ergeben (ohne Abruf).

Vallejo: 8429551 + Artikelnummer ohne Punkt + Prüfziffer, z. B. 74.265 -> 8429551742658.
Eingetragen mit ean_source "berechnet"; eine EAN vom Hersteller wird nie überschrieben.

Aufruf: python -m pipeline.derive_ean
"""
from __future__ import annotations

from .ean import vallejo_ean
from .lib import load_brand, save_brand

DERIVERS = {"vallejo": vallejo_ean}


def derive(slug: str) -> tuple[int, int]:
    """Gibt (neu eingetragen, Farben mit EAN) zurück."""
    brand = load_brand(slug)
    fn = DERIVERS[slug]
    taken = {p["ean"] for p in brand["paints"] if p.get("ean")}
    added = 0
    for p in brand["paints"]:
        if p.get("ean"):
            continue
        ean = fn(p.get("code"))
        if ean and ean not in taken:  # doppelte Codes (Altlasten) bekommen keine EAN
            p["ean"], p["ean_source"] = ean, "berechnet"
            taken.add(ean)
            added += 1
    save_brand(brand)
    return added, len(taken)


def main() -> int:
    for slug in DERIVERS:
        added, total = derive(slug)
        print(f"{slug:16} {added:4} EAN berechnet, {total} mit EAN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
