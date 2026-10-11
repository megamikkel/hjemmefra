import json
from datetime import datetime, timezone

from hjemmefra.catalog.resolver import ProductResolver
from hjemmefra.demo.dataset import NEGATIVE_ALIASES, PRODUCTS
from hjemmefra.domain.offer import ValidationStatus
from hjemmefra.ingestion.adapters.rema_public import RemaPublicPagesAdapter
from hjemmefra.ingestion.nuxt import Devalue
from hjemmefra.ingestion.pipeline import run_ingestion

NOW = datetime(2026, 10, 11, 6, tzinfo=timezone.utc)


def nuxt(products):
    """Build a devalue payload: flat array with index references."""
    arr = [["ShallowReactive", 1], {"data": 2}, []]
    def put(v):
        if isinstance(v, dict):
            idx = len(arr); arr.append(None)
            arr[idx] = {k: put(x) for k, x in v.items()}
            return idx
        if isinstance(v, list):
            idx = len(arr); arr.append(None)
            arr[idx] = [put(x) for x in v]
            return idx
        arr.append(v)
        return len(arr) - 1
    arr[2] = [put(p) for p in products]
    return '<script type="application/json" id="__NUXT_DATA__">' + json.dumps(arr) + "</script>"


BEEF = {"id": 1, "name": "HAKKET OKSEKØD 8-12%", "underline": "500 GR. / REMA 1000", "is_available_in_all_stores": True, "prices": [
    {"price": 35, "is_campaign": True, "is_advertised": True, "starting_at": "2026-10-11T00:00:00+00:00", "ending_at": "2026-10-17T00:00:00+00:00",
     "max_quantity": 3, "price_over_max_quantity": 49.95, "deposit": None},
    {"price": 49.95, "is_campaign": False, "starting_at": "2026-10-18T00:00:00+00:00", "ending_at": "2099-12-31T00:00:00+00:00"}]}
COLA = {"id": 2, "name": "COCA-COLA", "underline": "1,5 L / COCA-COLA", "is_available_in_all_stores": True, "prices": [
    {"price": 18, "is_campaign": False, "starting_at": "2026-01-01T00:00:00+00:00", "ending_at": "2099-12-31T00:00:00+00:00", "deposit": 3}]}
LOCAL = {"id": 3, "name": "LOKAL VARE", "underline": "1 KG", "is_available_in_all_stores": False, "prices": [
    {"price": 5, "is_campaign": False, "starting_at": "2026-01-01T00:00:00+00:00", "ending_at": "2099-12-31T00:00:00+00:00"}]}
PAGES = {"https://rema1000.dk/": nuxt([BEEF]) + '<a href="/opskrifter/chili">', "https://rema1000.dk/opskrifter": "",
         "https://rema1000.dk/opskrifter/chili": nuxt([COLA, LOCAL, BEEF])}


def test_devalue_roundtrip():
    import re
    data = json.loads(re.search(r">(.*)<", nuxt([BEEF])).group(1))
    p = next(Devalue(data).objects_with("prices", "name"))
    assert p["prices"][0]["max_quantity"] == 3


def test_rema_adapter_end_to_end():
    a = RemaPublicPagesAdapter(fetch_html=lambda u: (200, PAGES.get(u, "")), robots_txt="User-agent: *\nDisallow: /api/*\n", delay=0, now=NOW)
    report = run_ingestion([a], resolver=ProductResolver(PRODUCTS, NEGATIVE_ALIASES), now=NOW)
    titles = sorted(o.raw_title for o in report.offers)
    assert "Lokal vare 1 kg" not in titles  # store scope unknown -> skipped
    camp = next(o for o in report.offers if o.offer_price_minor == 3500)
    assert camp.normal_price_minor == 4995 and str(camp.valid_from) == "2026-10-11" and str(camp.valid_to) == "2026-10-16"
    assert camp.maximum_quantity == 3 and camp.package_quantity == 500 and camp.canonical_product_id == "BEEF_MINCED_8_12"
    assert camp.validation_status == ValidationStatus.NORMAL
    cola = next(o for o in report.offers if "Coca" in o.raw_title)
    assert cola.deposit_minor == 300 and str(cola.valid_to) == "2026-10-24"  # regular price capped to horizon
    assert cola.package_quantity == 1.5 and cola.package_unit.value == "l"
