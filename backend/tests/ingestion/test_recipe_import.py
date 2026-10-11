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
    assert p.unit.value == "stk" and "piece word" in p.note  # converted later via piece_size_estimate
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


def test_unquoted_type_and_microdata_fallback():
    from hjemmefra.recipes.importer import extract_recipe_node
    html = '<script type=application/ld+json>{"@type":"Recipe","name":"X","recipeIngredient":["1 løg"]}</script>'
    assert extract_recipe_node(html)["name"] == "X"
    md = '<h1>Frikadeller</h1><li itemprop="recipeIngredient">500 g <b>hakket svinekød</b></li><li itemprop="recipeIngredient">1 æg</li>'
    node = extract_recipe_node(md)
    assert node["name"] == "Frikadeller" and node["recipeIngredient"] == ["500 g hakket svinekød", "1 æg"]


def test_staples_garnish_and_piece_estimates_with_base_catalog():
    from hjemmefra.catalog.base_catalog import merged_catalog
    from hjemmefra.recipes.importer import recipe_from_jsonld
    resolver = ProductResolver(merged_catalog(PRODUCTS), NEGATIVE_ALIASES)
    node = {"@type": "Recipe", "name": "Test", "recipeYield": "4", "recipeIngredient": [
        "2 løg, finthakket", "2 fed hvidløg", "3 dl ris", "salt og friskkværnet peber", "2 spsk olivenolie",
        "1 håndfuld frisk koriander", "2 dåser kidneybønner", "500 g hakket oksekød",
        'div[itemprop="recipeInstructions"] > p.can-hover:hover{color:red}']}
    r = recipe_from_jsonld(node, "https://example.test/x", resolver).recipe
    by = {i.canonical_ingredient_id: i for i in r.ingredients}
    assert not r.review_required, [i.note for i in r.ingredients]
    assert by["ONION"].quantity == 300 and by["ONION"].unit.value == "g" and by["ONION"].quantity_is_estimate
    assert by["GARLIC"].quantity == 10 and by["BEANS_CANNED"].quantity == 800
    assert by["RICE"].unit.value == "dl" and by["RICE"].quantity_is_estimate
    assert by["SALT_PEPPER"].staple and by["COOKING_OIL"].staple and by["FRESH_HERBS"].optional
    assert len(r.ingredients) == 8  # CSS noise dropped


def test_staples_require_household_opt_in():
    from datetime import date
    from hjemmefra.catalog.base_catalog import merged_catalog
    from hjemmefra.demo.dataset import HOUSEHOLD
    from hjemmefra.domain.plan import PlanRequest
    from hjemmefra.planning.candidates import hard_filter
    from hjemmefra.recipes.importer import recipe_from_jsonld
    cat = merged_catalog(PRODUCTS)
    r = recipe_from_jsonld({"@type": "Recipe", "name": "T", "recipeIngredient": ["500 g hakket oksekød", "salt og peber"]},
                           "https://example.test/y", ProductResolver(cat)).recipe
    req = PlanRequest(household_id="x", start_date=date(2026, 10, 5), days=1)
    pm = {p.canonical_id: p for p in cat}
    hh = HOUSEHOLD.model_copy(deep=True)
    assert hard_filter(r, hh, pm, req) == "STAPLE_NOT_CONFIRMED:SALT_PEPPER"
    hh.preferences.has_basic_staples = True
    assert hard_filter(r, hh, pm, req) is None


def test_mixed_fractions():
    p = parse_ingredient_line("2½ dl cremefraiche 18 %")
    assert (p.quantity, p.unit.value, p.name) == (Decimal("2.5"), "dl", "cremefraiche")


def _plan_one(lines, **req_kw):
    from datetime import date
    from hjemmefra.catalog.base_catalog import merged_catalog
    from hjemmefra.demo.dataset import HOUSEHOLD
    from hjemmefra.domain.plan import PlanRequest
    from hjemmefra.planning.candidates import generate_candidates
    from hjemmefra.recipes.importer import recipe_from_jsonld
    cat = merged_catalog(PRODUCTS)
    node = {"@type": "Recipe", "name": "T", "recipeYield": "4", "totalTime": "PT30M", "recipeIngredient": lines}
    r = recipe_from_jsonld(node, "https://example.test/t", ProductResolver(cat, NEGATIVE_ALIASES)).recipe
    hh = HOUSEHOLD.model_copy(deep=True)
    hh.preferences.has_basic_staples = True
    req = PlanRequest(household_id="x", start_date=date(2026, 10, 12), days=1, **req_kw)
    pm = {p.canonical_id: p for p in cat}
    return r, generate_candidates([r], hh, pm, {}, {}, req, 4)


def test_side_dish_is_not_a_main_meal():
    r, (cands, rej) = _plan_one(["50 g bacon", "1 kg kartofler", "2 spsk olivenolie", "salt og peber"])
    assert r.main_protein == "PORK" and r.carbohydrate == "POTATO"
    assert rej and rej[0]["reason"].startswith("NOT_A_MAIN_MEAL:protein")


def test_unknown_time_never_passes_a_time_limit():
    from hjemmefra.recipes.importer import recipe_from_jsonld
    r = recipe_from_jsonld({"@type": "Recipe", "name": "T", "recipeIngredient": ["500 g hakket oksekød"]}, "https://e.test/u",
                           ProductResolver(PRODUCTS)).recipe
    assert r.time_known is False and r.total_minutes == 0
    from datetime import date
    from hjemmefra.demo.dataset import HOUSEHOLD, PRODUCT_MAP
    from hjemmefra.domain.plan import PlanRequest
    from hjemmefra.planning.candidates import hard_filter
    req = PlanRequest(household_id="x", start_date=date(2026, 10, 12), days=1, max_prep_minutes=45)
    assert hard_filter(r, HOUSEHOLD, PRODUCT_MAP, req) == "PREP_TIME_UNKNOWN"


def test_visible_time_labels_beat_swapped_hidden_schema():
    from hjemmefra.recipes.importer import extract_recipe_node, recipe_from_jsonld
    html = ('<div class="hidden-schema"><span itemprop="cookTime">PT3H</span><span itemprop="totalTime">PT40M</span>'
            '<span itemprop="recipeYield">6</span></div><h1>Lasagne</h1>'
            '<div>Tid i alt <span>3 timer</span><br>Arbejdstid <span>40 min.</span><br>Holdbarhed <span>2 dage</span>'
            '<br>Kan fryses <span>Ja</span></div><li itemprop="recipeIngredient">400 g hakket oksekød</li>')
    node = extract_recipe_node(html)
    r = recipe_from_jsonld(node, "https://e.test/l", ProductResolver(PRODUCTS)).recipe
    assert (r.total_minutes, r.prep_minutes, r.servings) == (180, 40, 6)
    assert r.time_known and r.leftover_friendly and r.freezer_friendly
    hidden_only = extract_recipe_node(html.split("<div>Tid")[0] + '<li itemprop="recipeIngredient">1 løg</li>')
    assert hidden_only["totalTime"] == "PT180M"  # larger hidden value taken as total, never the smaller
