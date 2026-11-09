"""Anreicherung mit meodai/color-names (MIT): nächster benannter Farbton pro Farbe.

Speichert pro Farbe: nearest_color_name = {name, hex, delta_e}
Suche: ΔE76 (vektorisiert, numpy) für die Top-K-Kandidaten, danach exakt mit CIEDE2000.

Aufruf: python -m pipeline.import_colornames [--src <pfad-oder-url zu colornames.csv>] [--good-only]
"""
from __future__ import annotations

import argparse
import csv
import io

import numpy as np

from .lib import (all_brand_slugs, delta_e2000, hex_to_rgb, load_brand, read_source,
                  rgb_to_lab, save_brand)

DEFAULT_SRC = "https://raw.githubusercontent.com/meodai/color-names/main/src/colornames.csv"
TOP_K = 8


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=DEFAULT_SRC)
    ap.add_argument("--good-only", action="store_true",
                    help="nur Namen mit 'good name'-Markierung verwenden (~5000 statt ~32000)")
    args = ap.parse_args(argv)

    rows = list(csv.DictReader(io.StringIO(read_source(args.src))))
    if args.good_only:
        rows = [r for r in rows if r.get("good name", "").strip()]
    names = [r["name"] for r in rows]
    hexes = [r["hex"].upper() for r in rows]
    labs = np.array([rgb_to_lab(hex_to_rgb(h)) for h in hexes])
    print(f"{len(names)} Farbnamen geladen")

    total = 0
    for slug in all_brand_slugs():
        brand = load_brand(slug)
        paints = [p for p in brand["paints"] if p.get("hex")]
        if not paints:
            continue
        plabs = np.array([rgb_to_lab(hex_to_rgb(p["hex"])) for p in paints])
        for start in range(0, len(paints), 512):
            chunk = plabs[start:start + 512]
            d = ((chunk[:, None, :] - labs[None, :, :]) ** 2).sum(-1)
            cand = np.argpartition(d, TOP_K, axis=1)[:, :TOP_K]
            for i, idxs in enumerate(cand):
                lab = tuple(chunk[i])
                best = min(idxs, key=lambda j: delta_e2000(lab, tuple(labs[j])))
                paints[start + i]["nearest_color_name"] = {
                    "name": names[best], "hex": hexes[best],
                    "delta_e": round(delta_e2000(lab, tuple(labs[best])), 2),
                }
        save_brand(brand)
        total += len(paints)
    print(f"{total} Farben angereichert")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
