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
            RecipeIngredient(canonical_ingredient_id="DRIED_SPICES", quantity=Decimal(1), unit=Unit.TSK)]
    rep = match_ingredients(ings, cat, [off("rice1kg", "RICE", 1, Unit.KG), off("spice_stk", "DRIED_SPICES", 1, Unit.STK)],
                            [STORES[0]], HOUSEHOLD, [date(2026, 10, 12)])
    assert rep.options["RICE"][0].package_base_qty == 1000  # grams, the product's base unit, not ml
    assert rep.options["DRIED_SPICES"] == []
    assert any(r.get("reason", "").startswith("UNIT_CONVERSION_UNKNOWN:stk->g") for r in rep.rejected)
