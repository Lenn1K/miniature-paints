"""Herstellerseiten abfragen und neue Produkte in data/brands/*.json eintragen.

Regeln:
  - Abgleich: 1) Code  2) Name + Serie  3) Name allein, wenn in der Marke eindeutig und kein Code
  - Abgleich 2b: Name in einer verwandten Serie (Product.match_sets), wenn die Altdaten dort keinen Code haben
  - Bekannte Farben: url, image, last_seen aktualisieren, fehlenden Code und fehlende EAN ergänzen
  - EAN: nie überschreiben, außer eine berechnete durch eine vom Hersteller; Abweichungen und
    Dubletten innerhalb der Marke stehen im Report
  - Neue Farben: status "new", hex null -> erscheinen im Report, nicht in den Markdown-Tabellen
  - Nichts wird gelöscht. Farben, die ein Scraper früher gesehen hat und die seit
    STALE_DAYS fehlen, werden nur im Report als "evtl. eingestellt" gelistet.

Aufruf:
  python -m pipeline.sync_shops                       # alle Scraper
  python -m pipeline.sync_shops --brands ak vallejo
  python -m pipeline.sync_shops --save-raw raw/       # Rohdaten sichern (Debug/Fixtures)
  python -m pipeline.sync_shops --from-raw raw/       # offline aus gesicherten Rohdaten
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import traceback
from datetime import date
from pathlib import Path

from .lib import TODAY, load_brand, make_id, norm_code, norm_name, save_brand, unique_id, write_report
from .scrape import SCRAPERS
from .scrape.base import Product

STALE_DAYS = 75  # > 30 Tage Fortschreib-Intervall von last_seen + Puffer
MAX_ENRICH = 50  # Obergrenze Detailseiten-Requests pro Lauf
EAN_SOURCE = {"vallejo": "berechnet"}  # Herkunft der EAN aus dem Scraper (Standard: hersteller)
MAX_EAN_LOOKUPS = 800  # Obergrenze EAN-Abfragen pro Lauf (Army Painter: eine Anfrage je Produkt)


def match(brand: dict, prod: Product) -> dict | None:
    paints = brand["paints"]
    if prod.code:
        nc = norm_code(prod.code)
        hits = [p for p in paints if norm_code(p.get("code")) == nc]
        if len(hits) == 1:
            return hits[0]
        if hits:  # gleicher Code in mehreren Serien (Altlasten) -> Serie entscheidet
            same_set = [p for p in hits if p.get("set") == prod.set]
            return (same_set or hits)[0]
    nn = norm_name(prod.name)
    hits = [p for p in paints if norm_name(p["name"]) == nn and p.get("set") == prod.set]
    if hits:
        return hits[0]
    if prod.code and prod.match_sets:
        hits = [p for p in paints if not p.get("code") and norm_name(p["name"]) == nn
                and p.get("set") in prod.match_sets]
        if len(hits) == 1:
            return hits[0]
    if not prod.code:
        hits = [p for p in paints if norm_name(p["name"]) == nn]
        if len(hits) == 1:
            return hits[0]
    return None


def set_ean(paint: dict, ean: str | None, source: str, taken: dict, conflicts: list) -> bool:
    """EAN eintragen, wenn sinnvoll. taken: EAN -> id innerhalb der Marke."""
    if not ean:
        return False
    old = paint.get("ean")
    if old == ean:
        if paint.get("ean_source") == "berechnet" and source != "berechnet":
            paint["ean_source"] = source
            return True
        return False
    if taken.get(ean, paint["id"]) != paint["id"]:
        conflicts.append(f"{ean} von {paint['id']} ({paint['name']}) gehört schon zu {taken[ean]}")
        return False
    if old and not (paint.get("ean_source") == "berechnet" and source != "berechnet"):
        conflicts.append(f"{paint['id']} ({paint['name']}): gespeichert {old}, {source} {ean}")
        return False
    if old:
        conflicts.append(f"{paint['id']} ({paint['name']}): berechnet {old} ersetzt durch {source} {ean}")
        taken.pop(old, None)
    paint["ean"], paint["ean_source"] = ean, source
    taken[ean] = paint["id"]
    return True


def sync_brand(slug: str, products: list[Product], scraper) -> dict:
    brand = load_brand(slug)
    ids = {p["id"] for p in brand["paints"]}
    taken = {p["ean"]: p["id"] for p in brand["paints"] if p.get("ean")}
    ean_source = EAN_SOURCE.get(slug, "hersteller")
    seen, new, updated, conflicts = set(), [], 0, []
    enrich_budget = MAX_ENRICH
    ean_budget = MAX_EAN_LOOKUPS
    lookup_errors = 0

    def lookup(prod: Product, current: str | None) -> None:
        nonlocal ean_budget, lookup_errors
        if prod.ean or current or ean_budget <= 0 or not hasattr(scraper, "lookup_ean"):
            return
        ean_budget -= 1
        try:
            prod.ean = scraper.lookup_ean(prod)
        except Exception:  # einzelne Produktseite kaputt -> beim nächsten Lauf wieder
            lookup_errors += 1

    for prod in products:
        p = match(brand, prod)
        if p is not None:
            lookup(prod, p.get("ean"))
            changed = set_ean(p, prod.ean, ean_source, taken, conflicts)
            for key, val in (("url", prod.url), ("image", prod.image)):
                if val and p.get(key) != val:
                    p[key] = val
                    changed = True
            if prod.code and not p.get("code"):
                p["code"] = prod.code
                changed = True
            # last_seen nur monatlich fortschreiben -> keine Diff-Flut in jedem Wochen-PR
            if not p.get("last_seen") or (date.fromisoformat(TODAY) - date.fromisoformat(p["last_seen"])).days >= 30:
                p["last_seen"] = TODAY
            updated += changed
            seen.add(p["id"])
            continue
        if scraper is not None and hasattr(scraper, "enrich") and enrich_budget > 0:
            try:
                prod = scraper.enrich(prod)
            except Exception as e:  # Detailseite kaputt -> mit Slug-Namen weitermachen
                prod.extra["enrich_error"] = str(e)
            enrich_budget -= 1
        lookup(prod, None)
        entry = {"name": prod.name, "code": prod.code, "set": prod.set, "hex": None,
                 "status": "new", "url": prod.url, "image": prod.image,
                 "first_seen": TODAY, "last_seen": TODAY}
        entry["id"] = unique_id(ids, make_id(slug, entry))
        ids.add(entry["id"])
        set_ean(entry, prod.ean, ean_source, taken, conflicts)
        brand["paints"].append(entry)
        seen.add(entry["id"])
        new.append(entry)
    stale = []
    for p in brand["paints"]:
        if p["id"] in seen or not p.get("last_seen") or p.get("status") == "discontinued":
            continue
        if (date.fromisoformat(TODAY) - date.fromisoformat(p["last_seen"])).days > STALE_DAYS:
            stale.append(p)
    save_brand(brand)
    return {"brand": brand["brand"], "found": len(products), "matched": len(seen) - len(new),
            "updated": updated, "new": new, "stale": stale, "conflicts": conflicts,
            "with_ean": sum(1 for p in brand["paints"] if p.get("ean")), "total": len(brand["paints"]),
            "ean_lookups": MAX_EAN_LOOKUPS - ean_budget, "lookup_errors": lookup_errors,
            "skipped": len(scraper.skipped) if scraper else 0,
            "unmapped": sorted(scraper.unmapped) if scraper else []}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brands", nargs="*", default=list(SCRAPERS))
    ap.add_argument("--save-raw", type=Path)
    ap.add_argument("--from-raw", type=Path)
    args = ap.parse_args(argv)

    results, errors = [], []
    for slug in args.brands:
        scraper = None
        try:
            if args.from_raw:
                raw = json.loads((args.from_raw / f"{slug}.json").read_text(encoding="utf-8"))
                products = [Product(**r) for r in raw]
            else:
                scraper = SCRAPERS[slug]()
                products = scraper.fetch()
                if args.save_raw:
                    args.save_raw.mkdir(parents=True, exist_ok=True)
                    (args.save_raw / f"{slug}.json").write_text(json.dumps(
                        [dataclasses.asdict(p) for p in products], ensure_ascii=False, indent=1),
                        encoding="utf-8")
            if not products:
                raise RuntimeError("0 Produkte gefunden – Seitenstruktur geändert oder blockiert?")
            results.append(sync_brand(slug, products, scraper))
            print(f"{slug:16} {len(products):4} gefunden, {len(results[-1]['new']):3} neu")
        except Exception as e:
            errors.append((slug, f"{type(e).__name__}: {e}"))
            print(f"{slug:16} FEHLER: {e}")
            traceback.print_exc()

    rep = [f"# Hersteller-Sync {TODAY}", "",
           "| Marke | gefunden | bekannt | aktualisiert | neu | evtl. eingestellt | übersprungen | mit EAN |",
           "|---|---|---|---|---|---|---|---|"]
    for r in results:
        ean = f"{r['with_ean']}/{r['total']}"
        if r["ean_lookups"]:
            ean += f" ({r['ean_lookups']} abgefragt, {r['lookup_errors']} Fehler)"
        rep.append(f"| {r['brand']} | {r['found']} | {r['matched']} | {r['updated']} | "
                   f"{len(r['new'])} | {len(r['stale'])} | {r['skipped']} | {ean} |")
    for slug, err in errors:
        rep.append(f"| {slug} | **Fehler:** {err} | | | | | | |")
    for r in results:
        if r["new"]:
            rep += ["", f"## {r['brand']}: neue Produkte (Farbwert fehlt)", "",
                    "| Code | Name | Serie | Link |", "|---|---|---|---|"]
            rep += [f"| {p['code'] or '–'} | {p['name']} | {p['set']} | [Shop]({p['url']}) |" for p in r["new"]]
        if r["conflicts"]:
            rep += ["", f"## {r['brand']}: EAN-Abweichungen (nichts überschrieben, außer berechnete)", ""]
            rep += [f"- {c}" for c in r["conflicts"][:100]]
        if r["unmapped"]:
            rep += ["", f"## {r['brand']}: unbekannte Serien/Titel (Mapping im Scraper ergänzen)", ""]
            rep += [f"- {u}" for u in r["unmapped"][:50]]
        if r["stale"]:
            rep += ["", f"## {r['brand']}: seit >{STALE_DAYS} Tagen nicht mehr im Shop", ""]
            rep += [f"- {p['code'] or ''} {p['name']} ({p['set']}), zuletzt {p['last_seen']}" for p in r["stale"]]
    path = write_report("sync-shops", rep)
    print(f"Report: {path}\n")
    print("\n".join(rep))  # auch ins Job-Log, damit der Bericht ohne Artefakt lesbar ist
    return 1 if errors and not results else 0


if __name__ == "__main__":
    raise SystemExit(main())
