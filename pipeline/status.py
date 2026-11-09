"""Übersicht als Markdown (für den Job Summary der Actions).

  python -m pipeline.status                 # Gesamtübersicht + offene Farben
  python -m pipeline.status --brand vallejo # nur eine Marke, mit allen offenen IDs
"""
from __future__ import annotations

import argparse
from collections import Counter

from .lib import all_brand_slugs, load_brand


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", default="")
    ap.add_argument("--limit", type=int, default=30, help="max. offene Farben pro Marke")
    a = ap.parse_args(argv)
    slugs = [a.brand] if a.brand else all_brand_slugs()

    rows, open_items = [], []
    total = Counter()
    for slug in slugs:
        b = load_brand(slug)
        c = Counter(p["status"] for p in b["paints"])
        no_hex = [p for p in b["paints"] if not p.get("hex")]
        alt = sum(1 for p in b["paints"] if p.get("alt_colors"))
        total.update(c)
        total["no_hex"] += len(no_hex)
        rows.append(f"| {b['brand']} | `{slug}` | {len(b['paints'])} | {c['active']} | {c['new']} | "
                    f"{c['discontinued']} | {len(no_hex)} | {alt} |")
        if no_hex:
            open_items.append((b["brand"], no_hex))

    out = ["## Farbdaten – Status", "",
           f"**{sum(total[s] for s in ('active', 'new', 'discontinued'))} Farben**, "
           f"davon {total['new']} neu/ungeprüft und {total['no_hex']} ohne Farbwert.", "",
           "| Marke | Slug | gesamt | aktiv | neu | eingestellt | ohne Farbwert | mit Alternativwert |",
           "|---|---|---|---|---|---|---|---|", *rows]
    if open_items:
        out += ["", "## Offene Farben (ohne Farbwert)", "",
                "ID kopieren und in der Action **Farbe bearbeiten** eintragen.", ""]
        for brand, items in open_items:
            out += [f"### {brand}", "", "| ID | Name | Serie | Kandidat | Link |", "|---|---|---|---|---|"]
            for p in items[:a.limit]:
                cand = ", ".join(f"`{x['hex']}` ({x['source'].split('/')[0]})" for x in p.get("alt_colors", []))
                link = f"[Shop]({p['url']})" if p.get("url") else ""
                out.append(f"| `{p['id']}` | {p['name']} | {p.get('set') or ''} | {cand} | {link} |")
            if len(items) > a.limit:
                out.append(f"| … | {len(items) - a.limit} weitere | | | |")
            out.append("")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
