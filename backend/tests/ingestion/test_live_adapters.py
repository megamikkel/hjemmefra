"""Live-source adapters tested against recorded fixtures (no network)."""
import json
from datetime import datetime, timezone
from pathlib import Path

from hjemmefra.catalog.resolver import ProductResolver
from hjemmefra.core.confidence import Confidence
from hjemmefra.demo.dataset import NEGATIVE_ALIASES, PRODUCTS
from hjemmefra.domain.offer import ValidationStatus
from hjemmefra.ingestion.adapters.salling import SallingFoodWasteAdapter, fetch_salling_stores
from hjemmefra.ingestion.adapters.tjek import TjekOffersAdapter
from hjemmefra.ingestion.base import SourceUnavailable
from hjemmefra.ingestion.packaging import parse_package
from hjemmefra.ingestion.pipeline import run_ingestion

FIX = Path(__file__).resolve().parents[2] / "fixtures" / "live"
NOW = datetime(2026, 10, 4, 6, tzinfo=timezone.utc)


def fake_fetch(path):
    def _f(url, headers, params):
        assert "Authorization" in headers or "X-Api-Key" in headers
        return json.loads((FIX / path).read_text())
    return _f


def test_parse_package():
    q, u, c = parse_package("Kyllingebrystfilet 900 g")
    assert (str(q), u.value, c) == ("900", "g", 1)
    q, u, c = parse_package("Hakkede tomater 2 x 400 g")
    assert (str(q), u.value, c) == ("400", "g", 2)
    assert parse_package("Blandet salat") is None
    assert parse_package("Fløde 250 ml, 38 g fedt") is None  # ambiguous -> unknown, never guessed


def test_salling_food_waste_maps_to_store_scoped_offers():
    adapter = SallingFoodWasteAdapter("tok", "4200", fetch=fake_fetch("salling_food_waste_4200.json"), now=NOW)
    report = run_ingestion([adapter], resolver=ProductResolver(PRODUCTS, NEGATIVE_ALIASES), now=NOW)
    assert not report.failed_sources and len(report.offers) == 4
    chicken = next(o for o in report.offers if "Kyllingebryst" in o.raw_title)
    assert chicken.scope.value == "STORE" and chicken.store_id == "salling_a1b2" and chicken.retailer == "netto"
    assert chicken.offer_price_minor == 2900 and chicken.normal_price_minor == 4900 and chicken.package_quantity == 900
    assert chicken.canonical_product_id == "CHICKEN_BREAST" and chicken.validation_status == ValidationStatus.NORMAL
    assert chicken.price_confidence == Confidence.VERIFIED
    salad = next(o for o in report.offers if "salat" in o.raw_title)
    assert salad.validation_status == ValidationStatus.REQUIRES_REVIEW  # unknown package + unmatched product
    assert any(r["type"] == "UNMATCHED_PRODUCT" for r in report.review_queue)


def test_salling_missing_token_is_graceful():
    adapter = SallingFoodWasteAdapter("", "4200", fetch=fake_fetch("salling_food_waste_4200.json"))
    r = adapter.fetch()
    assert not r.ok and "token" in r.error


def test_salling_http_error_is_graceful():
    def boom(url, headers, params):
        raise SourceUnavailable("HTTP 503")
    r = SallingFoodWasteAdapter("tok", "4200", fetch=boom).fetch()
    assert not r.ok and "503" in r.error


def test_salling_stores_import():
    def stores(url, headers, params):
        return [{"id": "a1b2", "name": "Netto Slagelse", "brand": "netto", "address": {"street": "Jernbanegade 1", "zip": "4200"},
                 "coordinates": [11.3546, 55.4027], "hours": []}]
    st = fetch_salling_stores("tok", "4200", fetch=stores)
    assert st[0].store_id == "salling_a1b2" and st[0].chain_id == "netto" and st[0].lat == 55.4027 and st[0].lon == 11.3546


def test_tjek_offers_mapping_and_unknown_dealer_skipped():
    pages = {0: json.loads((FIX / "tjek_offers_page1.json").read_text()), 1: []}
    calls = []

    def fetch(url, headers, params):
        calls.append(params)
        return pages[params["offset"] // params["limit"]]
    adapter = TjekOffersAdapter("key", 55.40, 11.35, 10000, "4200", fetch=fetch, now=NOW)
    report = run_ingestion([adapter], resolver=ProductResolver(PRODUCTS, NEGATIVE_ALIASES), now=NOW)
    titles = {o.raw_title: o for o in report.offers}
    assert "Vaskepulver" not in titles  # unknown dealer not in chain catalog
    beef = titles["Hakket oksekød 8-12%"]
    assert beef.retailer == "rema" and beef.scope.value == "REGIONAL" and beef.region == "tjek:4200"
    assert beef.offer_price_minor == 3500 and beef.normal_price_minor == 4995 and beef.package_quantity == 500
    assert beef.canonical_product_id == "BEEF_MINCED_8_12" and beef.validation_status == ValidationStatus.NORMAL
    chicken = titles["Kyllingefilet"]
    assert chicken.package_unit.value == "kg" and chicken.canonical_product_id == "CHICKEN_BREAST"
    pepper = titles["Peberfrugter"]
    assert pepper.package_quantity is None and pepper.validation_status == ValidationStatus.REQUIRES_REVIEW  # variable size
    assert pepper.normal_price_minor is None


def test_tjek_missing_key():
    assert "API key" in TjekOffersAdapter("", 1, 1, 1, "4200").fetch().error
