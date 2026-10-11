from decimal import Decimal
from pathlib import Path

from hjemmefra.catalog.resolver import ProductResolver
from hjemmefra.demo.dataset import NEGATIVE_ALIASES, PRODUCTS
from hjemmefra.recipes.importer import import_recipe_from_url, parse_ingredient_line

FIX = Path(__file__).resolve().parents[2] / "fixtures" / "live"


def test_parse_lines():
    p = parse_ingredient_line("500 g kyllingebrystfilet")
    assert (p.quantity, p.unit.value, p.name) == (Decimal(500), "g", "kyllingebrystfilet")
    p = parse_ingredient_line("2 løg")
    assert (p.quantity, p.unit.value, p.name) == (Decimal(2), "stk", "løg")
    p = parse_ingredient_line("1 dåse kokosmælk (400 ml)")
    assert p.unit is None and "container" in p.note
    p = parse_ingredient_line("½ dl fløde")
    assert p.quantity == Decimal("0.5") and p.unit.value == "dl"
    assert parse_ingredient_line("salt og peber").quantity is None


def test_import_from_jsonld_marks_review_for_unresolved():
    html = (FIX / "recipe_page.html").read_text()
    res = import_recipe_from_url("https://example.test/kylling-i-karry", ProductResolver(PRODUCTS, NEGATIVE_ALIASES), fetch_text=lambda u, h: html)
    r = res.recipe
    assert r is not None and r.name == "Kylling i karry med ris" and r.servings == 4 and r.prep_minutes == 10 and r.cook_minutes == 25
    assert r.source == "https://example.test/kylling-i-karry" and len(r.instructions) == 3
    ids = [i.canonical_ingredient_id for i in r.ingredients]
    assert ids[0] == "CHICKEN_BREAST" and ids[1] == "RICE"
    assert r.review_required  # coriander unmatched, "dåse" size unknown, "2 løg" stk vs g
    kinds = {i["type"] for i in res.review_items}
    assert "UNMATCHED_PRODUCT" in kinds and "UNIT_CONVERSION_UNKNOWN" in kinds


def test_review_required_recipe_is_excluded_from_planning():
    from hjemmefra.demo.dataset import HOUSEHOLD, PRODUCT_MAP, RECIPES
    from hjemmefra.domain.plan import PlanRequest
    from hjemmefra.planning.candidates import hard_filter
    from datetime import date
    r = RECIPES[0].model_copy(update={"review_required": True})
    assert hard_filter(r, HOUSEHOLD, PRODUCT_MAP, PlanRequest(household_id="x", start_date=date(2026, 10, 5), days=1)) == "REVIEW_REQUIRED"


def test_import_without_jsonld_fails_cleanly():
    res = import_recipe_from_url("https://example.test/none", ProductResolver(PRODUCTS), fetch_text=lambda u, h: "<html></html>")
    assert res.recipe is None and "JSON-LD" in res.error
