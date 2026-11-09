"""Import aus Ferror/vallejo-model-color-data (Vallejo Model Color, Quelle: offizielle Vallejo-Farbkarte).

- ergänzt spanische Namen (names.es)
- weicht der Farbwert ab (ΔE2000 > Schwelle), wird er als alt_colors-Eintrag abgelegt,
  der bestehende Wert bleibt (keine stillen Überschreibungen)
- fehlende Farben werden mit status "new" und ohne hex angelegt (Ferror-Wert nur als Kandidat)
- Highlight/Base/Shadow-Kombinationen -> data/combinations/vallejo-model-color.json

HINWEIS: Das Quell-Repo hat keine LICENSE-Datei. Für private Nutzung ok,
vor einer Veröffentlichung den Autor fragen.

Aufruf: python -m pipeline.import_ferror [--src <pfad-oder-url-zum-repo-root>]
"""
from __future__ import annotations

import argparse
import csv
import io
import json

from .lib import (DATA_DIR, TODAY, delta_e2000, load_brand, make_id, norm_code, rgb_to_hex,
                  rgb_to_lab, hex_to_rgb, save_brand, unique_id, write_report)

DEFAULT_SRC = "https://raw.githubusercontent.com/Ferror/vallejo-model-color-data/master"
SOURCE = "ferror/vallejo-model-color-data"
SET_NAME = "Model Color"
DELTA_E_THRESHOLD = 2.0  # darunter gilt die Abweichung als Rundungsrauschen


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=DEFAULT_SRC)
    args = ap.parse_args(argv)

    from .lib import read_source
    paints_csv = read_source(f"{args.src}/vallejo-model-color-all-paints.csv")
    combos_csv = read_source(f"{args.src}/vallejo-model-color-combinations.csv")

    brand = load_brand("vallejo")
    by_code = {norm_code(p["code"]): p for p in brand["paints"]
               if p.get("set") == SET_NAME and p.get("code") and "~" not in p["id"]}
    ids = {p["id"] for p in brand["paints"]}

    added, conflicts, enriched = [], [], 0
    code_to_id = {}
    for row in csv.DictReader(io.StringIO(paints_csv)):
        code = row["number"].strip()
        rgb = [int(x) for x in row["rgb"].replace(" ", "").split(",")]
        hx = rgb_to_hex(rgb)
        p = by_code.get(norm_code(code))
        if p is None:
            # Ferrors RGB-Werte sind stichprobenartig unzuverlässig (z. B. Desert Tan = Pink),
            # daher: neu anlegen, Farbwert nur als Kandidat, Status "new" bis geprüft.
            p = {"name": row["english_name"].strip(), "code": code, "set": SET_NAME,
                 "hex": None, "status": "new", "first_seen": TODAY,
                 "names": {"es": row["spanish_name"].strip()} if row.get("spanish_name") else {},
                 "alt_colors": [{"source": SOURCE, "hex": hx}]}
            p["id"] = unique_id(ids, make_id("vallejo", p))
            ids.add(p["id"])
            brand["paints"].append(p)
            added.append(f"| {code} | {p['name']} | `{hx}` (ungeprüft) |")
        else:
            if row.get("spanish_name"):
                p.setdefault("names", {})["es"] = row["spanish_name"].strip()
                enriched += 1
            if p["hex"] and p["hex"] != hx:
                de = delta_e2000(rgb_to_lab(hex_to_rgb(p["hex"])), rgb_to_lab(rgb))
                alts = [a for a in p.get("alt_colors", []) if a["source"] != SOURCE]
                if de > DELTA_E_THRESHOLD:
                    alts.append({"source": SOURCE, "hex": hx, "delta_e": round(de, 2)})
                    conflicts.append((de, f"| {code} | {p['name']} | `{p['hex']}` | `{hx}` | {de:.1f} |"))
                p["alt_colors"] = alts
            if row["english_name"].strip().lower() != p["name"].lower():
                p.setdefault("names", {})["en_alt"] = row["english_name"].strip()
        code_to_id[norm_code(code)] = p["id"]

    combos, missing = [], 0
    for row in csv.DictReader(io.StringIO(combos_csv)):
        triple = {k.lower(): code_to_id.get(norm_code(v)) for k, v in row.items()}
        if None in triple.values():
            missing += 1
            continue
        combos.append(triple)
    (DATA_DIR / "combinations").mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "combinations" / "vallejo-model-color.json").write_text(json.dumps({
        "source": SOURCE, "type": "highlight-base-shadow", "combinations": combos,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    save_brand(brand)

    rep = [f"# Import {SOURCE} ({TODAY})", "",
           f"- spanische Namen ergänzt: {enriched}",
           f"- neue Farben: {len(added)}",
           f"- Farbabweichungen > ΔE {DELTA_E_THRESHOLD}: {len(conflicts)} (als alt_colors abgelegt, nicht übernommen)",
           f"- Kombinationen: {len(combos)} (übersprungen: {missing})", ""]
    if added:
        rep += ["## Neu angelegt", "", "| Code | Name | Hex |", "|---|---|---|", *added, ""]
    if conflicts:
        rep += ["## Abweichungen (bestehend vs. Ferror)", "",
                "| Code | Name | bestehend | Ferror | ΔE2000 |", "|---|---|---|---|---|",
                *[c[1] for c in sorted(conflicts, reverse=True)], ""]
    path = write_report("import-ferror", rep)
    print("\n".join(rep[:7]))
    print(f"Report: {path.relative_to(path.parent.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
