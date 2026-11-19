"""Offline-Tests: Parser gegen Beispielpayloads im realen Format, Abgleich-Logik, Build."""
import json
import shutil

import pytest

import pipeline.lib as lib
from pipeline.scrape.ak import AKScraper
from pipeline.scrape.army_painter import ArmyPainterScraper
from pipeline.scrape.base import Product, smart_title
from pipeline.scrape.gsw import GreenStuffWorldScraper
from pipeline.scrape.vallejo import VallejoScraper


@pytest.fixture
def data_copy(tmp_path, monkeypatch):
    dst = tmp_path / "brands"
    shutil.copytree(lib.BRANDS_DIR, dst)
    monkeypatch.setattr(lib, "BRANDS_DIR", dst)
    monkeypatch.setattr(lib, "REPORTS_DIR", tmp_path / "reports")
    return dst


# ---------- Parser ----------

def test_army_painter_parse():
    s = ArmyPainterScraper()
    marker = {"title": "Speedpaint Marker: Magic Blue", "handle": "speedpaint-marker-magic-blue",
              "tags": ["SPEEDPAINT MARKER", "tap-shop", "tap-shop-paints", "tap-shop-paints-spm"],
              "variants": [{"sku": "SM1002P"}], "images": [{"src": "https://cdn/x.jpg"}]}
    p = s.parse(marker)
    assert (p.name, p.set, p.code) == ("Magic Blue", "Speedpaint Marker", "SM1002")
    assert s.parse({**marker, "title": "Speedpaint Marker: Expansion Set",
                    "variants": [{"sku": "BNDL212"}]}) is None
    assert s.parse({**marker, "title": "Speedpaint Marker: Replacement Tips"}) is None
    assert s.parse({**marker, "tags": ["tap-shop-bundle"]}) is None
    p = s.parse({**marker, "title": "Warpaints Air Metallics: Azure Magic", "variants": [{"sku": "AW1486P"}]})
    assert (p.set, p.code, p.match_sets) == ("Warpaints Air Metallics", "AW1486", ["Warpaints Air"])
    assert s.parse({**marker, "title": "Colour Primer: Ash Grey", "variants": [{"sku": "CP3029S"}]}).code == "CP3029"
    assert s.parse({**marker, "title": "Historical: Beret Maroon"}).set == "Warpaints Historical"
    assert s.parse({**marker, "title": "Warpaints Air: Gloss Varnish, 100 ml"}) is None
    assert not s.unmapped


def test_army_painter_lookup_ean(monkeypatch):
    s = ArmyPainterScraper()
    monkeypatch.setattr(s, "get_json", lambda url, **kw: {"variants": [{"barcode": ""}, {"barcode": "5713799200715"}]})
    assert s.lookup_ean(Product(name="x", set=None, extra={"handle": "h"})) == "5713799200715"
    monkeypatch.setattr(s, "get_json", lambda url, **kw: {"variants": [{"barcode": "123"}]})
    assert s.lookup_ean(Product(name="x", set=None, extra={"handle": "h"})) is None


def test_ak_parse():
    s = AKScraper()
    en = {"name": "WHITE &#8211; INTENSE", "sku": "AK11001",
          "permalink": "https://ak-interactive.com/product/white-intense/",
          "categories": [{"name": "3GEN ACRYLICS"}, {"name": "Intense"}], "images": []}
    p = s.parse(en, " (3rd Gen)")
    assert (p.name, p.set, p.code) == ("White", "Intense (3rd Gen)", "AK11001")
    es = {**en, "permalink": "https://ak-interactive.com/es/producto/white-intense/"}
    assert s.parse(es, " (3rd Gen)") is None
    assert s.parse({**en, "sku": "VIN-LW35067"}, " (3rd Gen)") is None
    kit = {**en, "sku": "AK11688", "name": "German WWII Tank Interior Colors",
           "categories": [{"name": "3GEN SETS B2B", "slug": "b2b-3gen-sets"}, {"name": "AFV Serie"}]}
    assert s.parse(kit, " (3rd Gen)") is None
    assert s.parse({**en, "name": "WHITE", "categories": [{"name": "Irgendwas"}]}, " (3rd Gen)") is None


def test_gsw_parse():
    s = GreenStuffWorldScraper()
    p = s.parse("Dipping ink 60 ml - ACID GREEN DIP", "u", "8435646508580ES", None)
    assert (p.name, p.set) == ("Acid Green Dip", "Dipping Inks")
    p = s.parse("Acrylic Color MOON MIST GREY", "u", None, None)
    assert (p.name, p.set) == ("Moon Mist Grey", "Acrylic Colors")
    assert s.parse("Empty Dropper Bottles 17ml with Mixing Balls", "u", None, None) is None
    assert s.parse("Opaque Acrylic Paint Set - Flesh Colours", "u", None, None) is None
    assert s.parse("Fluor Airbrush Paint - RED", "u", None, None).name == "Red"
    p = s.parse("Dipping ink 60 ml - ACID GREEN DIP", "u", "8435646508580ES", None)
    assert p.ean == "8435646508580"
    p = s.parse("Acrylic Ink Opaque- OSL WHITE", "u", None, None)
    assert (p.name, p.set, p.ean) == ("OSL White", "Opaque Acrylic Inks", None)
    assert s.parse("Fluor Acrylic Ink MAGENTA", "u", None, None).set == "Fluor Acrylic Inks"
    assert s.parse("Fluor ALIEN OOZE 10ml", "https://gsw/en/effect-paints/4934-x.html", None, None) is None
    assert s.parse("Metallic Paint COSMIC SILVER 17ml", "u", None, None).name == "Cosmic Silver"


def test_vallejo_parse_spanish_skipped():
    s = VallejoScraper()
    es = {"sku": "74.249", "name": "Acero Divino", "images": [],
          "permalink": "https://acrylicosvallejo.com/producto/modelismo/squidmar-color/acero-divino-74249/"}
    assert s.parse(es, "Squidmar Color") is None
    assert any("nicht englisch" in u for u in s.unmapped)


def test_vallejo_pick_api_rejects_spanish(monkeypatch):
    s = VallejoScraper()

    class R:
        def __init__(self, items): self.items = items
        def json(self): return self.items

    es = [{"permalink": "https://acrylicosvallejo.com/producto/x/"}]
    en = [{"permalink": "https://acrylicosvallejo.com/en/product/x/"}]
    calls = []

    def fake_get(url, params=None, **kw):
        calls.append((url, params.get("lang")))
        return R(en if params.get("lang") == "en" else es)

    monkeypatch.setattr(s, "get", fake_get)
    url, extra = s.pick_api()
    assert extra == {"lang": "en"} and len(calls) == 2
    monkeypatch.setattr(s, "get", lambda url, params=None, **kw: R(es))
    with pytest.raises(RuntimeError, match="keine englischen"):
        s.pick_api()


def test_vallejo_parse():
    s = VallejoScraper()
    item = {"sku": "71.242", "name": "Traffic Blue", "images": [],
            "permalink": "https://acrylicosvallejo.com/en/product/model-air-en/traffic-blue/",
            "categories": [{"slug": "model-air-en"}]}
    p = s.parse(item, "Model Air")
    assert (p.name, p.set, p.code) == ("Traffic Blue", "Model Air", "71.242")
    assert p.ean == "8429551712422"
    assert s.parse({**item, "sku": "76109"}, "Game Air").code == "76.109"
    assert s.parse({**item, "name": "Acrylic Gloss Spray Varnish"}, "Hobby Paint") is None
    assert s.parse({**item, "sku": "71.154", "name": "Bluelight Set"}, "Model Air") is None


def test_ean_helpers():
    from pipeline.ean import gsw_ean, is_valid_ean, normalize_ean, vallejo_ean
    assert vallejo_ean("74.265") == "8429551742658" and vallejo_ean("76109") == "8429551761093"
    assert vallejo_ean("AK11001") is None and vallejo_ean(None) is None
    assert is_valid_ean("8429551742658") and not is_valid_ean("8429551742659")
    assert is_valid_ean("96385074") and not is_valid_ean("12345")
    assert normalize_ean("036000291452") == "0036000291452"
    assert normalize_ean("8429551742659") is None
    assert gsw_ean("8435646508580es") == "8435646508580" and gsw_ean("ABC") is None


def test_smart_title():
    assert smart_title("MOON MIST GREY") == "Moon Mist Grey"
    assert smart_title("OSL WHITE") == "OSL White"
    assert smart_title("Moon Mist GREY") == "Moon Mist GREY"


# ---------- Abgleich ----------

def test_sync_matches_and_adds(data_copy):
    from pipeline.sync_shops import sync_brand
    products = [
        Product(name="White", set="Intense (3rd Gen)", code="AK11001", url="https://ak/white"),
        Product(name="Brand New Colour", set="Standard (3rd Gen)", code="AK19999", url="https://ak/new"),
    ]
    r = sync_brand("ak", products, None)
    assert r["matched"] == 1 and len(r["new"]) == 1
    brand = json.loads((data_copy / "ak.json").read_text())
    white = next(p for p in brand["paints"] if p["code"] == "AK11001")
    assert white["url"] == "https://ak/white" and white["hex"]          # Farbwert bleibt
    new = next(p for p in brand["paints"] if p["code"] == "AK19999")
    assert new["status"] == "new" and new["hex"] is None


def test_sync_fills_missing_code_by_name(data_copy):
    from pipeline.sync_shops import sync_brand
    brand = json.loads((data_copy / "army-painter.json").read_text())
    target = next(p for p in brand["paints"] if not p["code"] and p["set"] == "Warpaints Fanatic")
    r = sync_brand("army-painter", [Product(name=target["name"], set="Warpaints Fanatic", code="WP3999")], None)
    assert r["matched"] == 1 and not r["new"]
    brand = json.loads((data_copy / "army-painter.json").read_text())
    assert next(p for p in brand["paints"] if p["id"] == target["id"])["code"] == "WP3999"


def test_sync_match_sets(data_copy):
    from pipeline.sync_shops import sync_brand
    brand = json.loads((data_copy / "army-painter.json").read_text())
    target = next(p for p in brand["paints"] if not p["code"] and p["set"] == "Warpaints Air")
    prod = Product(name=target["name"], set="Warpaints Air Metallics", code="AW1999", match_sets=["Warpaints Air"])
    r = sync_brand("army-painter", [prod], None)
    assert r["matched"] == 1 and not r["new"]
    # ohne verwandte Serie -> neue Farbe (z. B. Speedpaint Marker mit gleichem Namen wie ein Topf)
    other = Product(name=target["name"], set="Speedpaint Marker", code="SM1999")
    assert len(sync_brand("army-painter", [other], None)["new"]) == 1


def test_sync_ean(data_copy):
    from pipeline.sync_shops import sync_brand
    products = [Product(name="White", set="Intense (3rd Gen)", code="AK11001", ean="8435568303102"),
                Product(name="Brand New", set="Standard (3rd Gen)", code="AK19999", ean="8435568303102")]
    r = sync_brand("ak", products, None)
    brand = {p["code"]: p for p in json.loads((data_copy / "ak.json").read_text())["paints"]}
    assert (brand["AK11001"]["ean"], brand["AK11001"]["ean_source"]) == ("8435568303102", "hersteller")
    assert "ean" not in brand["AK19999"] and len(r["conflicts"]) == 1   # Dublette
    assert r["with_ean"] == sum(1 for p in lib.load_brand("ak")["paints"] if p.get("ean"))
    # gespeicherte Hersteller-EAN wird nicht überschrieben
    r = sync_brand("ak", [Product(name="White", set="Intense (3rd Gen)", code="AK11001", ean="8429551742658")], None)
    assert r["conflicts"] and json.loads((data_copy / "ak.json").read_text())


def test_sync_ean_lookup_budget(data_copy, monkeypatch):
    import pipeline.sync_shops as ss

    class Fake:
        skipped, unmapped = [], set()
        calls = 0

        def lookup_ean(self, prod):
            Fake.calls += 1
            return "5713799200715"

    monkeypatch.setattr(ss, "MAX_EAN_LOOKUPS", 1)
    before = sum(1 for p in lib.load_brand("army-painter")["paints"] if p.get("ean"))
    prods = [Product(name="Neu A", set="Warpaints", code="WP9998"), Product(name="Neu B", set="Warpaints", code="WP9999")]
    r = ss.sync_brand("army-painter", prods, Fake())
    assert Fake.calls == 1 and r["ean_lookups"] == 1 and r["with_ean"] == before + 1


def test_derive_ean(data_copy):
    from pipeline.derive_ean import derive
    added, total = derive("vallejo")
    assert added == 0   # schon im Repo
    p = next(x for x in lib.load_brand("vallejo")["paints"] if x["code"] == "70.951")
    assert (p["ean"], p["ean_source"]) == ("8429551709514", "berechnet")


def test_sync_name_match_needs_missing_code(data_copy):
    from pipeline.sync_shops import sync_brand
    brand = json.loads((data_copy / "vallejo.json").read_text())
    target = next(p for p in brand["paints"] if p["code"] and p["status"] == "active")
    r = sync_brand("vallejo", [Product(name=target["name"], set=target["set"], code="99.999")], None)
    assert not r["matched"] and len(r["new"]) == 1
    after = next(p for p in lib.load_brand("vallejo")["paints"] if p["id"] == target["id"])
    assert after.get("url") == target.get("url")


def test_get_retries_connection_errors(monkeypatch):
    import requests
    import pipeline.scrape.base as base
    monkeypatch.setattr(base.time, "sleep", lambda s: None)
    s = base.Scraper()
    calls = []

    class Ok:
        status_code = 200
        def raise_for_status(self): pass

    def fake(url, **kw):
        calls.append(url)
        if len(calls) < 3:
            raise requests.ConnectionError("Remote end closed connection")
        return Ok()

    monkeypatch.setattr(s.session, "get", fake)
    assert s.get("https://x").status_code == 200 and len(calls) == 3
    calls.clear()
    monkeypatch.setattr(s.session, "get", lambda url, **kw: (_ for _ in ()).throw(requests.ConnectionError("x")))
    with pytest.raises(requests.ConnectionError):
        s.get("https://x")


# ---------- Build ----------

def test_markdown_up_to_date():
    """paints/*.md müssen dem Build-Ergebnis entsprechen (CI-Check)."""
    from pipeline.build import build_md
    for slug in lib.all_brand_slugs():
        b = lib.load_brand(slug)
        assert (lib.ROOT / "paints" / b["md_file"]).read_text(encoding="utf-8") == build_md(b), slug


def test_compact_brand_files():
    """dist/brands/<slug>.json: klein genug für Apps mit 2-MB-Limit, ohne eingestellte Farben."""
    from pipeline.build import compact
    for slug in lib.all_brand_slugs():
        b = lib.load_brand(slug)
        path = lib.DIST_DIR / "brands" / f"{slug}.json"
        assert json.loads(path.read_text(encoding="utf-8")) == compact(b), slug
        assert path.stat().st_size < 1_000_000, slug
    c = compact({"brand": "X", "slug": "x", "paints": [
        {"name": "A", "code": None, "set": "S", "hex": "#000000", "status": "active", "url": "u"},
        {"name": "B", "code": "1", "set": None, "hex": None, "status": "discontinued"}]})
    assert c["paints"] == [{"name": "A", "set": "S", "hex": "#000000", "status": "active"}]


def test_release_tag_and_summary():
    from datetime import date
    from pipeline.release_notes import next_tag, notes, summarize
    d = date(2026, 11, 19)
    assert next_tag(d, []) == ("data-2026-11-19", "Farbdaten 19.11.2026")
    assert next_tag(d, ["data-2026-11-19", "data-2026-11-19.2"]) == ("data-2026-11-19.3", "Farbdaten 19.11.2026 (3)")
    old = {"brand": "X", "paints": [{"name": "A", "code": "1"}, {"name": "Gone", "code": "9"}]}
    new = {"brand": "X", "paints": [{"name": "A", "code": "1", "ean": "4006381333931", "hex": "#000000"},
                                    {"name": "B", "set": "S"}]}
    r = summarize(new, old)
    assert (r["count"], r["hex"], r["ean"], r["ean_added"]) == (2, 1, 1, 1)
    assert [p["name"] for p in r["added"]] == ["B"] and [p["name"] for p in r["removed"]] == ["Gone"]
    first = summarize(new, None)
    assert not first["added"] and "Erster" in notes([first], None)
    assert "| X | 2 | 1 | 1 | 1 | 1 |" in notes([r], "data-2026-11-01")


# ---------- Bearbeiten ----------

def test_edit_paint(data_copy):
    from pipeline.edit_paint import main
    assert main(["--id", "vallejo/70-757", "--hex", "5a746b"]) == 0
    p = next(x for x in lib.load_brand("vallejo")["paints"] if x["id"] == "vallejo/70-757")
    assert (p["hex"], p["status"], p["color_source"]) == ("#5A746B", "active", "manuell")
    assert main(["--id", "vallejo/70-748", "--use-alt", "ferror/vallejo-model-color-data"]) == 0
    assert main(["--id", "vallejo/70-747", "--hex", "xyz"]) == 1
    assert main(["--id", "vallejo/70-747", "--status", "active"]) == 1   # active ohne hex
    assert main(["--id", "vallejo/gibtsnicht"]) == 1
