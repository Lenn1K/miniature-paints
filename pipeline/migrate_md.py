"""Einmalige Migration: paints/*.md -> data/brands/*.json

Danach ist JSON die Quelle; die Markdown-Dateien werden von build.py erzeugt.
Aufruf: python -m pipeline.migrate_md
"""
from __future__ import annotations

import re
import sys

from .lib import BRANDS_DIR, ROOT, hex_to_rgb, make_id, rgb_to_hex, save_brand, slugify, unique_id

PAINTS_DIR = ROOT / "paints"
HEX_RE = re.compile(r"`(#[0-9A-Fa-f]{6})`")


def parse_md(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    title = next(l[2:].strip() for l in lines if l.startswith("# "))
    header = None
    rows = []
    for line in lines:
        if not line.startswith("|") or line.startswith("|---"):
            continue
        cells = [c.strip() for c in line.strip()[1:-1].split("|")]
        if header is None:
            header = cells
            continue
        rows.append(dict(zip(header, cells)))
    return title, header, rows


def main() -> int:
    if any(BRANDS_DIR.glob("*.json")) and "--force" not in sys.argv:
        print("data/brands/ existiert bereits – mit --force überschreiben.")
        return 1
    problems = []
    for md in sorted(PAINTS_DIR.glob("*.md")):
        title, header, rows = parse_md(md)
        slug = slugify(md.stem)
        ids: set[str] = set()
        paints = []
        for r in rows:
            code = r.get("Code")
            code = None if not code or code.lower() == "null" else code
            m = HEX_RE.search(r.get("Hex", ""))
            rgb = [int(r["R"]), int(r["G"]), int(r["B"])]
            if m and rgb_to_hex(rgb) != m.group(1).upper():
                problems.append(f"{md.name}: {r['Name']} RGB {rgb} != Hex {m.group(1)}")
            if not r["Name"]:
                problems.append(f"{md.name}: leerer Name bei Code {code} – Code als Name übernommen")
            paint = {
                "name": r["Name"] or code or "?",
                "code": code,
                "set": r.get("Set") or None,
                "hex": rgb_to_hex(rgb),
                "status": "active",
                "color_source": "miniaturepainterpro",
            }
            pid = make_id(slug, paint)
            if pid in ids:
                problems.append(f"{md.name}: doppelte ID {pid} ({r['Name']} / {r.get('Set')})")
            paint["id"] = unique_id(ids, pid)
            ids.add(paint["id"])
            paints.append(paint)
        save_brand({
            "brand": title,
            "slug": slug,
            "md_file": md.name,
            "logo": f"logos/{md.stem}.png",
            "columns": [c for c in header if c in ("Name", "Code", "Set", "R", "G", "B", "Hex")],
            "paints": paints,
        })
        print(f"{md.name:28} {len(paints):5} Farben")
    if problems:
        print(f"\n{len(problems)} Hinweise:")
        for p in problems:
            print("  " + p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
