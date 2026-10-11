from hjemmefra.catalog.resolver import ProductResolver
from hjemmefra.core.confidence import MatchConfidence
from hjemmefra.demo.dataset import NEGATIVE_ALIASES, PRODUCTS


def test_resolver_aliases():
    r = ProductResolver(PRODUCTS, NEGATIVE_ALIASES)
    assert r.resolve("Kyllingebrystfilet").canonical_id == "CHICKEN_BREAST"
    assert r.resolve("Kyllingefilet 900 g").confidence == MatchConfidence.HIGH
    assert r.resolve("Brystfilet af kylling, 2 pk").canonical_id == "CHICKEN_BREAST"


def test_whole_chicken_is_not_chicken_breast():
    r = ProductResolver(PRODUCTS, NEGATIVE_ALIASES)
    res = r.resolve("Hel kylling 1,2 kg")
    assert res.canonical_id == "WHOLE_CHICKEN"


def test_unmatched_returns_unmatched():
    r = ProductResolver(PRODUCTS, NEGATIVE_ALIASES)
    assert r.resolve("Opvasketabs 60 stk").confidence == MatchConfidence.UNMATCHED


def test_alias_must_match_whole_words():
    r = ProductResolver(PRODUCTS, NEGATIVE_ALIASES)
    assert r.resolve("frisk koriander").confidence == MatchConfidence.UNMATCHED
    assert r.resolve("Jasminris 1 kg").canonical_id == "RICE"


def test_package_expressed_in_product_base_unit_and_bad_units_rejected():
    from datetime import date, datetime, timezone
    from decimal import Decimal
    from hjemmefra.catalog.base_catalog import merged_catalog
    from hjemmefra.core.confidence import Confidence
    from hjemmefra.core.units import Unit
    from hjemmefra.demo.dataset import HOUSEHOLD, STORES
    from hjemmefra.domain.offer import NormalizedOffer, SourceType, ValidationStatus
    from hjemmefra.domain.recipe import RecipeIngredient
    from hjemmefra.domain.store import OfferScope
    from hjemmefra.matching.ingredient_product import match_ingredients
    now = datetime(2026, 10, 11, tzinfo=timezone.utc)
    cat = {p.canonical_id: p for p in merged_catalog(PRODUCTS)}

    def off(oid, cid, q, u):
        return NormalizedOffer(offer_id=oid, raw_id="r", source_id="s", source_type=SourceType.PUBLIC_PAGE, source_reference="x",
                               captured_at=now, last_verified_at=now, retailer="rema", scope=OfferScope.NATIONAL,
                               valid_from=date(2026, 10, 11), valid_to=date(2026, 10, 17), raw_title=oid, canonical_product_id=cid,
                               match_confidence=MatchConfidence.HIGH, package_quantity=Decimal(q), package_unit=u, offer_price_minor=895,
                               price_confidence=Confidence.HIGH, validation_status=ValidationStatus.NORMAL)
    ings = [RecipeIngredient(canonical_ingredient_id="RICE", quantity=Decimal(3), unit=Unit.DL),
            RecipeIngredient(canonical_ingredient_id="FLOUR", quantity=Decimal(1), unit=Unit.SPSK)]
    rep = match_ingredients(ings, cat, [off("rice1kg", "RICE", 1, Unit.KG), off("flour_stk", "FLOUR", 1, Unit.STK)],
                            [STORES[0]], HOUSEHOLD, [date(2026, 10, 12)])
    assert rep.options["RICE"][0].package_base_qty == 1000  # grams, the product's base unit, not ml
    assert rep.options["FLOUR"] == []
    assert any(r.get("reason", "").startswith("UNIT_CONVERSION_UNKNOWN:stk->g") for r in rep.rejected)


REAL_TITLES = [  # (retailer title seen on 2026-10-11, expected canonical id or None)
    ("Pasta sauce 480 gr.", None), ("Tomat pasta 140 gr.", "TOMATO_PASTE"), ("Spaghetti 1 kg.", "PASTA"),
    ("Ris/mandel drik 1 ltr.", None), ("Basmati ris 1 kg.", "RICE"), ("GOLDEN SUN Basmatiris", "RICE"),
    ("Kondenseret mælk 397 gr.", None), ("Letmælk 1,5% fedt 1 ltr.", "MILK"),
    ("Tun i vand 140 gr.", "TUNA"), ("BELLAROM Espresso hele bønner", None), ("Edamame bønner 300 gr.", "EDAMAME"),
    ("Chili con carne 450 gr.", None), ("Rød peber 1 stk.", "BELL_PEPPER"), ("Sort peber 50 gr.", "SALT_PEPPER"),
    ("Squash appelsin-is i bæger", None), ("Z syltede agurker 190 gr.", None), ("Grøn te med citron 24 gr.", None),
    ("Croutoner, hvidløg 75 gr.", None), ("Risotto med spinat 400 gr.", None), ("Tortilla chips salt 200 gr.", None),
    ("chef select Paneret kyllingebrystfilet", None), ("Kyllingebrystfilet 450 gr.", "CHICKEN_BREAST"),
    ("Hakket oksekød 8-12% 500 gr.", "BEEF_MINCED_8_12"), ("Jasminris 1 kg", "RICE"),
]


def test_real_retailer_titles_resolve_safely():
    from hjemmefra.catalog.base_catalog import merged_catalog
    r = ProductResolver(merged_catalog(PRODUCTS), NEGATIVE_ALIASES)
    bad = []
    for title, expected in REAL_TITLES:
        res = r.resolve(title)
        got = res.canonical_id if res.confidence in (MatchConfidence.HIGH, MatchConfidence.MEDIUM) else None
        if got != expected:
            bad.append((title, expected, got, res.confidence.value))
    assert not bad, bad


def test_piece_sold_vegetables_use_documented_piece_estimate():
    from datetime import date, datetime, timezone
    from decimal import Decimal
    from hjemmefra.catalog.base_catalog import merged_catalog
    from hjemmefra.core.confidence import Confidence
    from hjemmefra.core.units import Unit
    from hjemmefra.demo.dataset import HOUSEHOLD, STORES
    from hjemmefra.domain.offer import NormalizedOffer, SourceType, ValidationStatus
    from hjemmefra.domain.recipe import RecipeIngredient
    from hjemmefra.domain.store import OfferScope
    from hjemmefra.matching.ingredient_product import match_ingredients
    now = datetime(2026, 10, 11, tzinfo=timezone.utc)
    cat = {p.canonical_id: p for p in merged_catalog(PRODUCTS)}
    o = NormalizedOffer(offer_id="squash", raw_id="r", source_id="s", source_type=SourceType.PUBLIC_PAGE, source_reference="x",
                        captured_at=now, last_verified_at=now, retailer="rema", scope=OfferScope.NATIONAL, valid_from=date(2026, 10, 11),
                        valid_to=date(2026, 10, 17), raw_title="Squash 1 stk.", canonical_product_id="ZUCCHINI",
                        match_confidence=MatchConfidence.HIGH, package_quantity=Decimal(1), package_unit=Unit.STK, offer_price_minor=800,
                        price_confidence=Confidence.HIGH, validation_status=ValidationStatus.NORMAL)
    rep = match_ingredients([RecipeIngredient(canonical_ingredient_id="ZUCCHINI", quantity=Decimal(300), unit=Unit.G)], cat, [o],
                            [STORES[0]], HOUSEHOLD, [date(2026, 10, 12)])
    opt = rep.options["ZUCCHINI"][0]
    assert opt.package_base_qty == 300 and "anslået" in opt.explanation
