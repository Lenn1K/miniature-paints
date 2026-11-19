"""Release-Notizen für einen Datenstand (dist/brands/*.json) erzeugen.

Ein Release heißt „Farbdaten TT.MM.JJJJ“ mit Tag data-JJJJ-MM-TT (am selben Tag: .2, .3 …).
Verglichen wird mit dem letzten data-*-Tag. Hat sich dist/brands/ seitdem nicht geändert,
gibt es kein Release (skip=true) – so darf der Workflow ruhig mehrfach laufen.

Aufruf (im Workflow): python -m pipeline.release_notes --out release.md >> "$GITHUB_OUTPUT"
Ausgabe auf stdout: skip=…, tag=…, title=…
"""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import date
from pathlib import Path

from .lib import DIST_DIR, ROOT

BRANDS_DIR = DIST_DIR / "brands"
# Marken, die die Label-Suite lädt: zuerst und ausführlich
FEATURED = ["vallejo", "army-painter", "ak", "greenstuffworld"]
MAX_LISTED = 20  # neue Farben je Marke in den Notizen


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout


def data_tags() -> list[str]:
    """data-*-Tags, neuester zuerst."""
    return [t for t in git("tag", "--list", "data-*", "--sort=-creatordate").split() if t]


def next_tag(day: date, existing: list[str]) -> tuple[str, str]:
    """('data-2026-11-19', 'Farbdaten 19.11.2026'), am selben Tag mit .2, .3 …"""
    base, title = f"data-{day.isoformat()}", f"Farbdaten {day.strftime('%d.%m.%Y')}"
    if base not in existing:
        return base, title
    n = 2
    while f"{base}.{n}" in existing:
        n += 1
    return f"{base}.{n}", f"{title} ({n})"


def key(p: dict) -> str:
    return f"#{p['code'].lower()}" if p.get("code") else f"{p['name'].lower()}|{(p.get('set') or '').lower()}"


def summarize(new: dict, old: dict | None) -> dict:
    """Zahlen einer Marke und was seit dem letzten Stand dazukam bzw. wegfiel."""
    paints = new["paints"]
    before = {key(p): p for p in (old or {}).get("paints", [])}
    now = {key(p): p for p in paints}
    return {
        "brand": new["brand"], "count": len(paints),
        "hex": sum(1 for p in paints if p.get("hex")), "ean": sum(1 for p in paints if p.get("ean")),
        "added": [p for k, p in now.items() if k not in before] if old else [],
        "removed": [p for k, p in before.items() if k not in now] if old else [],
        "ean_added": sum(1 for k, p in now.items() if p.get("ean") and not before.get(k, {}).get("ean")) if old else 0,
    }


def brand_at(tag: str, slug: str) -> dict | None:
    try:
        return json.loads(git("show", f"{tag}:dist/brands/{slug}.json"))
    except subprocess.CalledProcessError:
        return None


def notes(rows: list[dict], prev: str | None) -> str:
    lines = [f"Vergleich mit {prev}." if prev else "Erster veröffentlichter Datenstand.", "",
             "| Marke | Farben | mit Farbwert | mit EAN | neu | entfernt |", "|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['brand']} | {r['count']} | {r['hex']} | {r['ean']} | "
                     f"{len(r['added']) if prev else '–'} | {len(r['removed']) if prev else '–'} |")
    for r in rows:
        if r["added"]:
            lines += ["", f"**{r['brand']}: neu**", ""]
            lines += [f"- {p.get('code') or '–'} {p['name']} ({p.get('set') or '–'})" for p in r["added"][:MAX_LISTED]]
            if len(r["added"]) > MAX_LISTED:
                lines.append(f"- … und {len(r['added']) - MAX_LISTED} weitere")
    lines += ["", "In der Label-Suite: Einstellungen → Catalog → Paint list „Own list“ → Version wählen → "
              "„Save and update catalog“. Zurück: vorige Version wählen."]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    tags = data_tags()
    prev = tags[0] if tags else None
    if prev and not git("diff", "--name-only", prev, "HEAD", "--", "dist/brands").strip():
        print("skip=true")
        return 0
    slugs = sorted(p.stem for p in BRANDS_DIR.glob("*.json"))
    slugs = [s for s in FEATURED if s in slugs] + [s for s in slugs if s not in FEATURED]
    rows = []
    for s in slugs:
        r = summarize(json.loads((BRANDS_DIR / f"{s}.json").read_text(encoding="utf-8")), brand_at(prev, s) if prev else None)
        if s in FEATURED or r["added"] or r["removed"]:
            rows.append(r)
    tag, title = next_tag(date.today(), tags)
    args.out.write_text(notes(rows, prev), encoding="utf-8")
    print(f"skip=false\ntag={tag}\ntitle={title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
