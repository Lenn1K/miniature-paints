"""Offline-Tests: Parser gegen Beispielpayloads im realen Format, Abgleich-Logik, Build."""
import json
import shutil

import pytest

import pipeline.lib as lib
from pipeline.scrape.ak import AKScraper
from pipeline.scrape.army_painter import ArmyPainterScraper
from pipeline.scrape.base import Product, smart_title
from pipeline.scrape.gsw import GreenStuffWorldScraper
from pipeline.scrape.vallejo import PRODUCT_RE, code_from_digits


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


def test_gsw_parse():
    s = GreenStuffWorldScraper()
    p = s.parse("Dipping ink 60 ml - ACID GREEN DIP", "u", "8435646508580ES", None)
    assert (p.name, p.set) == ("Acid Green Dip", "Dipping Inks")
    p = s.parse("Acrylic Color MOON MIST GREY", "u", None, None)
    assert (p.name, p.set) == ("Moon Mist Grey", "Acrylic Colors")
    assert s.parse("Empty Dropper Bottles 17ml with Mixing Balls", "u", None, None) is None
    assert s.parse("Opaque Acrylic Paint Set - Flesh Colours", "u", None, None) is None


def test_vallejo_url():
    m = PRODUCT_RE.search("https://acrylicosvallejo.com/en/product/hobby/model-color/white-70951/")
    assert (m["range"], m["slug"], code_from_digits(m["code"])) == ("model-color", "white", "70.951")


def test_smart_title():
    assert smart_title("MOON MIST GREY") == "Moon Mist Grey"
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


# ---------- Build ----------

def test_markdown_up_to_date():
    """paints/*.md müssen dem Build-Ergebnis entsprechen (CI-Check)."""
    from pipeline.build import build_md
    for slug in lib.all_brand_slugs():
        b = lib.load_brand(slug)
        assert (lib.ROOT / "paints" / b["md_file"]).read_text(encoding="utf-8") == build_md(b), slug
