"""Einzelne Farbe bearbeiten – gedacht für die GitHub Action "Farbe bearbeiten".

  python -m pipeline.edit_paint --id vallejo/70-757 --hex "#5A746B" --status active
  python -m pipeline.edit_paint --id ak/ak11001 --name "White" --set "Intense (3rd Gen)"
  python -m pipeline.edit_paint --id vallejo/70-757 --use-alt ferror/vallejo-model-color-data

Setzt man einen hex-Wert bei einer Farbe mit status "new", wird sie automatisch "active".
"""
from __future__ import annotations

import argparse
import re
import sys

from .lib import load_brand, save_brand

STATUSES = ("active", "new", "discontinued")


def fail(msg: str) -> int:
    print(f"::error::{msg}")
    return 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--hex", default="")
    ap.add_argument("--use-alt", default="", help="Farbwert aus alt_colors dieser Quelle übernehmen")
    ap.add_argument("--status", default="", choices=("", "unverändert", *STATUSES))
    ap.add_argument("--name", default="")
    ap.add_argument("--set", default="")
    ap.add_argument("--code", default="")
    ap.add_argument("--source", default="manuell", help="color_source bei neuem Farbwert")
    a = ap.parse_args(argv)

    pid = a.id.strip()
    if "/" not in pid:
        return fail(f"ID '{pid}' hat kein Format <marke>/<…>")
    slug = pid.split("/", 1)[0]
    try:
        brand = load_brand(slug)
    except FileNotFoundError:
        return fail(f"Marke '{slug}' gibt es nicht")
    paint = next((p for p in brand["paints"] if p["id"] == pid), None)
    if paint is None:
        close = [p["id"] for p in brand["paints"] if pid.split("/", 1)[1] in p["id"]][:5]
        return fail(f"ID '{pid}' nicht gefunden" + (f" – meintest du {', '.join(close)}?" if close else ""))

    before = dict(paint)
    hx = a.hex.strip()
    if a.use_alt:
        alt = next((x for x in paint.get("alt_colors", []) if x["source"] == a.use_alt), None)
        if not alt:
            return fail(f"Kein alt_colors-Eintrag der Quelle '{a.use_alt}'")
        hx, a.source = alt["hex"], a.use_alt
        paint["alt_colors"] = [x for x in paint["alt_colors"] if x is not alt]
    if hx:
        hx = "#" + hx.lstrip("#").upper()
        if not re.fullmatch(r"#[0-9A-F]{6}", hx):
            return fail(f"'{a.hex}' ist kein gültiger Hex-Wert (#RRGGBB)")
        paint["hex"] = hx
        paint["color_source"] = a.source
        paint.pop("nearest_color_name", None)  # wird beim nächsten Import neu berechnet
        if paint.get("status") == "new" and a.status in ("", "unverändert"):
            paint["status"] = "active"
    if a.status not in ("", "unverändert"):
        paint["status"] = a.status
    for field in ("name", "set", "code"):
        val = getattr(a, field).strip()
        if val:
            paint[field] = val
    if paint.get("status") == "active" and not paint.get("hex"):
        return fail("status 'active' ohne Farbwert – erst hex setzen")

    changes = [f"| {k} | {before.get(k)} | {paint.get(k)} |"
               for k in ("name", "code", "set", "hex", "status", "color_source") if before.get(k) != paint.get(k)]
    if not changes:
        print("Keine Änderung.")
        return 0
    save_brand(brand)
    print(f"### {pid}\n\n| Feld | vorher | nachher |\n|---|---|---|\n" + "\n".join(changes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
