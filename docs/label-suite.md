# Datenformat für die Label-Suite

Die Label-Suite (privates Repo `Lenn1K/thermo-printer-suite`) lädt ihren Farbkatalog aus diesem Repo.
Diese Datei beschreibt, was sie erwartet. Wer am Build, an den Dateien unter `dist/brands/` oder am
Release-Workflow etwas ändert, prüft es gegen diese Liste. `tests/test_pipeline.py::test_label_suite_contract`
prüft die wichtigsten Punkte automatisch.

Stand: Label-Suite mit „Eigene Farbliste“ und Versionsauswahl (November 2026). Maßgeblich im Code der Suite:
`server/src/catalog/source.ts` (Dateien, Version), `server/src/catalog/parse.ts` (`parseBrandList`),
`server/src/catalog/releases.ts` (`parseReleases`).

## Wie die Suite liest

- Nur auf Knopfdruck („Update catalog“), serverseitig, SSRF-sicher.
- Adresse: `https://raw.githubusercontent.com/Lenn1K/miniature-paints/<ref>/dist/brands/<slug>.json`
- `<ref>` ist immer ein **Tag oder Commit**, nie ein Branch. Erlaubt: `^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$`
  (kein Schrägstrich). Ältere Tags müssen also lesbar bleiben – **Tags nie löschen oder verschieben.**
- Pro Datei höchstens **2 MB**, HTTP 200, Content-Type `text/*` (raw.githubusercontent.com liefert `text/plain`),
  höchstens 3 Weiterleitungen auf denselben Host.
- Schlägt eine Datei fehl oder ist sie unbrauchbar, scheitert die ganze Liste; die Suite behält dann
  ihren bisherigen Katalog.

## Dateien

Genau diese vier, alle müssen in jeder Version vorhanden sein:

| Datei | Marke in der Suite |
|---|---|
| `dist/brands/vallejo.json` | Vallejo |
| `dist/brands/army-painter.json` | Army Painter |
| `dist/brands/ak.json` | AK Interactive |
| `dist/brands/greenstuffworld.json` | Green Stuff World |

Die Marke nimmt die Suite aus dieser Tabelle, nicht aus dem Feld `brand` der Datei. Eine neue Marke
braucht also eine Änderung in der Suite (`FORK_FILES`); Dateien weiterer Marken stören nicht.
Umbenennen oder Entfernen einer der vier Dateien bricht die Suite.

## Inhalt einer Datei

Beispiel mit erfundenen Werten:

```json
{
  "brand": "Vallejo",
  "slug": "vallejo",
  "paints": [
    { "name": "Example Red", "code": "10.001", "set": "Example Series", "hex": "#A32F26", "ean": "4006381333931", "status": "active" },
    { "name": "Example New", "code": "10.002", "set": "Example Series", "status": "new" }
  ]
}
```

| Feld | Pflicht | Regel in der Suite | Sonst |
|---|---|---|---|
| `paints` | ja | Array | Datei ungültig („No paint list“) |
| `name` | ja | Text, nach Zusammenfassen der Leerzeichen 1–80 Zeichen | Eintrag wird übersprungen |
| `code` | nein | Herstellernummer, 1–20 Zeichen; wird Artikelnummer | ohne Artikelnummer übernommen |
| `set` | nein | Serie, 1–40 Zeichen | ohne Serie übernommen |
| `hex` | nein | genau `#RRGGBB` (Groß/klein egal) | ohne Farbwert übernommen |
| `ean` | nein | 8 oder 13 Ziffern mit gültiger Prüfziffer, als **String** | ohne EAN übernommen |
| `status` | nein | wird nicht gelesen | – |

- Leere Werte weglassen. Die Texte `null`, `n/a` und `-` gelten als leer.
- Weitere Felder werden ignoriert, dürfen also dazukommen.
- Doppelte Einträge: Gleiche `code` (ohne Groß/klein) oder, ohne Code, gleiches `name` + `set` – nur der
  **erste** zählt. Darum Farben mit bekanntem Code nicht zusätzlich ohne Code führen.
- Mindestens ein brauchbarer Eintrag, höchstens 5000 pro Datei.
- Eingestellte Farben (`status: discontinued`) lässt der Build schon weg.
- Die Suite kennt hier nur Farben. Basing-Material (Texturen, Pigmente …) bekommt sie aus anderen Quellen;
  es gehört nicht in diese Dateien.
- Eine EAN ist in der Suite der Schlüssel für den Barcode-Scan. Sie muss je Marke eindeutig und richtig sein;
  lieber keine als eine geratene (berechnete Vallejo-EANs: `ean_source: "berechnet"` in `data/brands/`).

## Releases (Auswahl in der Suite)

Die Suite zeigt die **drei neuesten** Releases als Auswahl „Version of the own list“. Sie liest
`https://api.github.com/repos/Lenn1K/miniature-paints/releases` und nimmt nur Releases, die

- einen Tag beginnend mit `data-` haben, der zur `<ref>`-Regel oben passt,
- weder Entwurf (`draft`) noch Vorabversion (`prerelease`) sind.

Sortiert wird nach `published_at`, angezeigt wird der Release-Name (bis 80 Zeichen, sonst der Tag).
Der Workflow „Release: Datenstand“ erzeugt das passend: Tag `data-JJJJ-MM-TT` (am selben Tag `.2`, `.3` …),
Name „Farbdaten TT.MM.JJJJ“. Andere Releases (z. B. `v1.0`) stören nicht, erscheinen aber nicht.

Ohne Version in den Einstellungen nutzt die Suite `data-2026-11-19` – dieser Tag muss bestehen bleiben.

## Prüfliste vor einer Änderung

- [ ] Die vier Dateien entstehen weiter unter `dist/brands/` mit den Feldern oben.
- [ ] Jede Datei bleibt deutlich unter 2 MB (Test: < 1 MB).
- [ ] `ean` als String, gültige Prüfziffer, je Marke eindeutig.
- [ ] Keine Tags gelöscht oder verschoben; neue Datenstände bekommen neue `data-*`-Tags.
- [ ] Ändert sich das Format inkompatibel, zuerst die Suite anpassen (Parser akzeptiert dann beides) und erst
      danach hier umstellen – ältere Releases bleiben ja auswählbar.
