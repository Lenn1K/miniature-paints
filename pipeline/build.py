"""Erzeugt aus data/brands/*.json:
  - paints/<Marke>.md      (gleiches Format wie das Original-Repo)
  - dist/paints.json       (flache Liste für die App)
  - dist/brands.json       (Markenübersicht)
  - README-Markenübersicht zwischen <!-- START --> / <!-- END -->

Aufruf: python -m pipeline.build
"""
from __future__ import annotations

import json
import re

from .lib import DIST_DIR, ROOT, all_brand_slugs, hex_to_rgb, load_brand

PAINTS_DIR = ROOT / "paints"

# Attribution des Original-Repos (MIT) beibehalten
FOOTER = [
    '<p align="center"><img src="../logos/logo_rnd.png" height="70" /></p>',
    '<p align="center">Made available by <a href="https://miniaturepainterpro.app/">Miniature Painter Pro</a></p>',
    '<p align="center">',
    '<a href="https://play.google.com/store/apps/details?id=com.rfsp.paintmaster"> <img src="../logos/Android.png" height="30" /></a>',
    '<a href="https://apps.apple.com/us/app/miniature-painter-pro/id1495938928"> <img src="../logos/iOS.png" height="30" /></a>',
    '</p>',
]


def md_row(p: dict, columns: list[str]) -> str:
    hx = p["hex"]
    rgb = hex_to_rgb(hx) if hx else ["", "", ""]
    swatch = f"![{hx}](https://placehold.co/15x15/{hx[1:]}/{hx[1:]}.png) `{hx}`" if hx else ""
    values = {
        "Name": p["name"], "Code": p["code"] or "null", "Set": p["set"] or "",
        "R": str(rgb[0]), "G": str(rgb[1]), "B": str(rgb[2]), "Hex": swatch,
    }
    return "|" + "|".join(values[c] for c in columns) + "|"


def build_md(brand: dict) -> str:
    cols = brand["columns"]
    stem = brand["md_file"][:-3]
    lines = [
        f"# {brand['brand']}",
        f'![{stem}](../{brand["logo"]} "{stem}")',
        "",
        "|" + "|".join(cols) + "|",
        "|" + "|".join("---" for _ in cols) + "|",
    ]
    # Nur Farben mit Farbwert gehören in die Tabelle
    paints = [p for p in brand["paints"] if p["hex"] and p["status"] != "discontinued"]
    for p in sorted(paints, key=lambda p: p["name"]):
        lines.append(md_row(p, cols))
    return "\n".join(lines + FOOTER) + "\n"


def readme_table(brands: list[dict]) -> str:
    cells = []
    for b in brands:
        cells.append(f'  <a href="paints/{b["md_file"]}"> <img src="{b["logo"]}" height="70" /> <br/> {b["brand"]}</a>')
    rows = ["|  |  |  |", "| :---: | :---: | :---: |"]
    for i in range(0, len(cells), 3):
        rows.append("|" + "|".join(cells[i:i + 3]) + "|")
    return "\n".join(rows)


def main() -> int:
    brands = [load_brand(s) for s in all_brand_slugs()]
    PAINTS_DIR.mkdir(exist_ok=True)
    DIST_DIR.mkdir(exist_ok=True)
    flat = []
    for b in brands:
        (PAINTS_DIR / b["md_file"]).write_text(build_md(b), encoding="utf-8")
        for p in b["paints"]:
            flat.append({"brand": b["brand"], "brand_slug": b["slug"], **p,
                         "rgb": hex_to_rgb(p["hex"]) if p["hex"] else None})
    (DIST_DIR / "paints.json").write_text(
        json.dumps(flat, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    (DIST_DIR / "brands.json").write_text(json.dumps([
        {"brand": b["brand"], "slug": b["slug"], "logo": b["logo"], "count": len(b["paints"])}
        for b in brands], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    readme = ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")
    brands_sorted = sorted(brands, key=lambda b: b["md_file"])
    text = re.sub(r"<!-- START -->.*?<!-- END -->",
                  lambda _: "<!-- START -->\n" + readme_table(brands_sorted) + "\n<!-- END -->",
                  text, flags=re.S)
    readme.write_text(text, encoding="utf-8")
    print(f"{len(brands)} Marken, {len(flat)} Farben -> paints/, dist/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
