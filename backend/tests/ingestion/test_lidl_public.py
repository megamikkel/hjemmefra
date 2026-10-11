import html
import json
from datetime import datetime, timezone

from hjemmefra.catalog.resolver import ProductResolver
from hjemmefra.core.confidence import Confidence
from hjemmefra.demo.dataset import HOUSEHOLD, NEGATIVE_ALIASES, PRODUCTS
from hjemmefra.domain.household import Membership
from hjemmefra.domain.offer import ValidationStatus
from hjemmefra.ingestion.adapters.lidl_public import LidlPublicPagesAdapter, _packaging
from hjemmefra.ingestion.pipeline import run_ingestion
from hjemmefra.pricing.engine import eligibility

NOW = datetime(2026, 10, 11, 6, tzinfo=timezone.utc)
START, END = 1791756000, 1792360799  # 2026-10-12 00:00 .. 2026-10-18 23:59:59 Copenhagen


def tile(**kw):
    d = {"productId": kw.pop("pid"), "fullTitle": kw.pop("title"), "storeStartDate": START, "storeEndDate": END,
         "keyfacts": {"wonCategoryPrimary": kw.pop("cat", "Mad og mad i nærheden/Kød & fjerkræ")}}
    d.update(kw)
    return '<div data-grid-data="' + html.escape(json.dumps(d)) + '"></div>'


HUB = ('<a href="/c/ugens-koed-og-fisk/a10104855">kød</a><a href="/1/forbudt/a123">x</a>'
       + tile(pid=1, title="Hakket oksekød 8-12%", price={"price": 35, "packaging": {"text": "500 g"}, "basePrice": {"text": "Pr. kg 70,00"}})
       + tile(pid=2, title="Grillpølser", lidlPlus=[{"price": {"price": 15, "packaging": {"text": "2 x 100 g"}}, "highlightText": "Kuponpris"}])
       + tile(pid=3, title="Kontorstol", cat="Hjem/Møbler", price={"price": 399, "packaging": {"text": "1 stk"}}))
CAMPAIGN = tile(pid=4, title="Kalvecuvette", price={"price": 69, "packaging": {"text": "1/2 kg"}})
PAGES = {"https://www.lidl.dk/c/tilbudsavis/s10013730": HUB, "https://www.lidl.dk/c/ugens-koed-og-fisk/a10104855": CAMPAIGN}


def fake(url):
    return (200, PAGES[url]) if url in PAGES else (404, "")


def test_packaging_parsing():
    assert _packaging("1/2 kg")[:3] == (0.5, "kg", 1)
    assert _packaging("24 x 330 ml")[:3] == (330, "ml", 24)
    assert _packaging("ca. 1 kg")[3] is True
    assert _packaging("Pr. stk") is None


def test_lidl_adapter_end_to_end():
    a = LidlPublicPagesAdapter(fetch_html=fake, robots_txt="User-agent: *\nDisallow: /1*\n", delay=0, now=NOW)
    report = run_ingestion([a], resolver=ProductResolver(PRODUCTS, NEGATIVE_ALIASES), now=NOW)
    by = {o.raw_title: o for o in report.offers}
    assert set(by) == {"Hakket oksekød 8-12%", "Grillpølser", "Kalvecuvette"}  # non-food filtered, campaign page followed
    beef = by["Hakket oksekød 8-12%"]
    assert beef.offer_price_minor == 3500 and beef.package_quantity == 500 and beef.normal_price_minor is None
    assert str(beef.valid_from) == "2026-10-12" and str(beef.valid_to) == "2026-10-18"
    assert beef.canonical_product_id == "BEEF_MINCED_8_12" and beef.validation_status == ValidationStatus.NORMAL
    assert beef.price_confidence == Confidence.HIGH and beef.source_type.value == "PUBLIC_PAGE"
    plus = by["Grillpølser"]
    assert plus.member_only and plus.required_membership == "lidl_plus" and plus.coupon_required
    assert plus.package_quantity == 100 and plus.package_count == 2
    hh = HOUSEHOLD.model_copy(deep=True)
    assert eligibility(plus, hh) == "MEMBERSHIP_REQUIRED:lidl_plus"
    hh.memberships = [Membership(program_id="lidl_plus", has_digital_coupons=True)]
    assert eligibility(plus, hh) is None
    assert by["Kalvecuvette"].package_quantity == 0.5 and by["Kalvecuvette"].package_unit.value == "kg"


def test_lidl_robots_disallow_and_failure():
    a = LidlPublicPagesAdapter(fetch_html=lambda u: (503, ""), robots_txt="", delay=0, now=NOW)
    r = a.fetch()
    assert not r.ok and "503" in r.error
