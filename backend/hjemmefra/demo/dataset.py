"""Deterministic demo dataset: 3 stores, ~25 offers, 20 products, 12 recipes, 1 household.

All prices are fictional but realistic. Used by tests (golden cases) and the
demo seed. Week: Monday 2026-10-05 .. Sunday 2026-10-11; shopping on Monday.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from hjemmefra.core.units import Unit
from hjemmefra.domain.household import Allergen, Household, HouseholdMember, Location, Membership, Preferences
from hjemmefra.domain.offer import SourceType
from hjemmefra.domain.pantry import InventoryLot, InventorySource, InventoryState
from hjemmefra.domain.product import CanonicalProduct, ProductAttributes, StorageType
from hjemmefra.domain.recipe import Recipe, RecipeIngredient
from hjemmefra.domain.store import Chain, Store
from hjemmefra.ingestion.base import ComplianceClass, SourceDescriptor

WEEK_START = date(2026, 10, 5)
CAPTURED_AT = datetime(2026, 10, 4, 6, 0, tzinfo=timezone.utc)

CHAINS = [Chain(chain_id="rema", name="REMA 1000"), Chain(chain_id="lidl", name="Lidl", membership_program_id="lidl_plus"),
          Chain(chain_id="netto", name="Netto", membership_program_id="salling_plus")]

STORES = [
    Store(store_id="rema_aarhus_n", chain_id="rema", name="REMA 1000 Aarhus N", postal_code="8200", region="midtjylland", lat=56.1880, lon=10.1850),
    Store(store_id="lidl_aarhus_n", chain_id="lidl", name="Lidl Aarhus N", postal_code="8200", region="midtjylland", lat=56.1830, lon=10.1750),
    Store(store_id="netto_risskov", chain_id="netto", name="Netto Risskov", postal_code="8240", region="midtjylland", lat=56.2010, lon=10.2250),
    Store(store_id="netto_odense", chain_id="netto", name="Netto Odense C", postal_code="5000", region="syddanmark", lat=55.3959, lon=10.3883),
]


def _p(cid, name, cat, unit, aliases=(), shelf=None, storage=StorageType.CHILLED, protein=None, allergens=(), sub=None,
       veg=True, vegan=False, fat=None, density=None):
    return CanonicalProduct(canonical_id=cid, name=name, category=cat, aliases=list(aliases), base_unit=unit,
                            attributes=ProductAttributes(storage=storage, vegetarian=veg, vegan=vegan,
                                                         fat_percentage=Decimal(str(fat)) if fat is not None else None),
                            allergens=list(allergens), estimated_shelf_life_days=shelf, protein_group=protein,
                            substitution_group=sub, density_g_per_ml=Decimal(str(density)) if density else None)


PRODUCTS = [
    _p("CHICKEN_BREAST", "Kyllingebryst", "meat", Unit.G, ["kyllingebrystfilet", "kyllingefilet", "brystfilet af kylling"], 4, protein="CHICKEN", veg=False),
    _p("WHOLE_CHICKEN", "Hel kylling", "meat", Unit.G, ["hel kylling", "kylling hel"], 4, protein="CHICKEN", veg=False),
    _p("BEEF_MINCED_8_12", "Hakket oksekød 8-12 %", "meat", Unit.G, ["hakket oksekød 8-12%", "hakket oksekød"], 3, protein="BEEF", veg=False, fat=10, sub="MINCED_MEAT"),
    _p("BEEF_MINCED_14_18", "Hakket oksekød 14-18 %", "meat", Unit.G, ["hakket oksekød 14-18%"], 3, protein="BEEF", veg=False, fat=16, sub="MINCED_MEAT"),
    _p("PORK_MINCED", "Hakket svinekød", "meat", Unit.G, ["hakket svinekød", "hakket grisekød"], 3, protein="PORK", veg=False, fat=12),
    _p("SALMON_FILLET", "Laksefilet", "fish", Unit.G, ["laks", "laksefilet"], 2, protein="FISH", allergens=[Allergen.FISH], veg=False),
    _p("PASTA", "Pasta", "dry", Unit.G, ["spaghetti", "penne", "fuldkornspasta"], 365, StorageType.AMBIENT, allergens=[Allergen.GLUTEN], vegan=True),
    _p("RICE", "Ris", "dry", Unit.G, ["jasminris", "basmati", "grødris"], 365, StorageType.AMBIENT, vegan=True),
    _p("POTATO", "Kartofler", "vegetables", Unit.G, ["kartoffel", "bagekartofler"], 14, StorageType.AMBIENT, vegan=True),
    _p("ONION", "Løg", "vegetables", Unit.G, ["løg", "zittauerløg"], 21, StorageType.AMBIENT, vegan=True),
    _p("TOMATO_CANNED", "Hakkede tomater", "canned", Unit.G, ["hakkede tomater", "flåede tomater"], 730, StorageType.AMBIENT, vegan=True),
    _p("COCONUT_MILK", "Kokosmælk", "canned", Unit.ML, ["kokosmælk"], 730, StorageType.AMBIENT, vegan=True, density=1.0),
    _p("CURRY_PASTE", "Karrypasta", "spices", Unit.G, ["rød karrypasta", "karry pasta"], 365, StorageType.AMBIENT, vegan=True),
    _p("CREAM", "Fløde", "dairy", Unit.ML, ["piskefløde", "madlavningsfløde"], 7, allergens=[Allergen.MILK, Allergen.LACTOSE], density=1.0),
    _p("CHEESE_GRATED", "Revet ost", "dairy", Unit.G, ["revet mozzarella", "revet ost"], 14, allergens=[Allergen.MILK, Allergen.LACTOSE]),
    _p("EGGS", "Æg", "dairy", Unit.STK, ["æg", "skrabeæg", "frilandsæg"], 21, allergens=[Allergen.EGG]),
    _p("BROCCOLI", "Broccoli", "vegetables", Unit.G, ["broccoli"], 5, vegan=True),
    _p("BELL_PEPPER", "Peberfrugt", "vegetables", Unit.G, ["peberfrugt", "peberfrugter"], 7, vegan=True),
    _p("CHICKPEAS_CANNED", "Kikærter", "canned", Unit.G, ["kikærter"], 730, StorageType.AMBIENT, vegan=True, protein="VEG"),
    _p("TORTILLA", "Tortillas", "bread", Unit.STK, ["tortilla", "hvedetortillas"], 30, StorageType.AMBIENT, allergens=[Allergen.GLUTEN], vegan=True),
    _p("TACO_SPICE", "Tacokrydderi", "spices", Unit.G, ["taco spice mix", "tacokrydderi"], 365, StorageType.AMBIENT, vegan=True),
    _p("BEANS_CANNED", "Bønner", "canned", Unit.G, ["sorte bønner", "kidneybønner"], 730, StorageType.AMBIENT, vegan=True, protein="VEG"),
    _p("LENTILS", "Linser", "dry", Unit.G, ["røde linser", "grønne linser"], 365, StorageType.AMBIENT, vegan=True, protein="VEG"),
]
PRODUCT_MAP = {p.canonical_id: p for p in PRODUCTS}

NEGATIVE_ALIASES = {"CHICKEN_BREAST": ["hel kylling", "kyllingelår", "kyllingevinger"]}

SOURCES = {
    "rema": SourceDescriptor("demo_rema", SourceType.DEMO, ComplianceClass.USER_SUPPLIED, "rema"),
    "lidl": SourceDescriptor("demo_lidl", SourceType.DEMO, ComplianceClass.USER_SUPPLIED, "lidl"),
    "netto": SourceDescriptor("demo_netto", SourceType.DEMO, ComplianceClass.USER_SUPPLIED, "netto"),
}

VF, VT = "2026-10-05", "2026-10-11"


def _o(ext, retailer, title, cid, qty, unit, normal, offer=None, **kw):
    d = {"external_id": ext, "retailer": retailer, "title": title, "canonical_product_id": cid, "scope": "NATIONAL",
         "valid_from": VF, "valid_to": VT, "package_quantity": str(qty), "package_unit": unit, "package_count": 1,
         "normal_price": str(normal), "offer_price": str(offer) if offer is not None else str(normal)}
    d.update(kw)
    return d


RAW_OFFERS = [
    # --- REMA (national offers) ---
    _o("r1", "rema", "Kyllingebrystfilet 900 g", "CHICKEN_BREAST", 900, "g", "79.00", "55.00"),
    _o("r2", "rema", "Hakket oksekød 8-12% 500 g", "BEEF_MINCED_8_12", 500, "g", "49.95", "35.00"),
    _o("r3", "rema", "Pasta 500 g", "PASTA", 500, "g", "12.00"),
    _o("r4", "rema", "Jasminris 1 kg", "RICE", 1000, "g", "22.00"),
    _o("r5", "rema", "Hakkede tomater 400 g", "TOMATO_CANNED", 400, "g", "8.00", "6.00", multi_buy_quantity=3, multi_buy_price="15.00", offer_price=None),
    _o("r6", "rema", "Kokosmælk 400 ml", "COCONUT_MILK", 400, "ml", "14.00", "10.00"),
    _o("r7", "rema", "Løg 1 kg", "ONION", 1000, "g", "12.00"),
    _o("r8", "rema", "Kartofler 2 kg", "POTATO", 2000, "g", "20.00", "15.00"),
    _o("r9", "rema", "Piskefløde 250 ml", "CREAM", 250, "ml", "14.00"),
    _o("r10", "rema", "Æg 10 stk", "EGGS", 10, "stk", "32.00", "25.00"),
    _o("r11", "rema", "Broccoli 400 g", "BROCCOLI", 400, "g", "15.00"),
    _o("r12", "rema", "Hvedetortillas 8 stk", "TORTILLA", 8, "stk", "15.00"),
    _o("r13", "rema", "Tacokrydderi 30 g", "TACO_SPICE", 30, "g", "8.00"),
    _o("r14", "rema", "Kikærter 400 g", "CHICKPEAS_CANNED", 400, "g", "9.00"),
    _o("r15", "rema", "Revet mozzarella 200 g", "CHEESE_GRATED", 200, "g", "22.00"),
    _o("r16", "rema", "Rød karrypasta 100 g", "CURRY_PASTE", 100, "g", "18.00"),
    _o("r17", "rema", "Røde linser 500 g", "LENTILS", 500, "g", "18.00"),
    # --- LIDL ---
    _o("l1", "lidl", "Kyllingefilet 1 kg", "CHICKEN_BREAST", 1000, "g", "85.00", "60.00"),
    _o("l2", "lidl", "Hakket oksekød 8-12% 400 g", "BEEF_MINCED_8_12", 400, "g", "42.00", "30.00", multi_buy_quantity=2, multi_buy_price="50.00", offer_price=None),
    _o("l3", "lidl", "Laksefilet 400 g", "SALMON_FILLET", 400, "g", "69.00", "45.00"),
    _o("l4", "lidl", "Penne 500 g", "PASTA", 500, "g", "9.00"),
    _o("l5", "lidl", "Basmati 1 kg", "RICE", 1000, "g", "19.00"),
    _o("l6", "lidl", "Hakkede tomater 400 g", "TOMATO_CANNED", 400, "g", "7.00"),
    _o("l7", "lidl", "Peberfrugt 3 stk 450 g", "BELL_PEPPER", 450, "g", "18.00", "12.00"),
    _o("l8", "lidl", "Bagekartofler 2 kg", "POTATO", 2000, "g", "18.00"),
    _o("l9", "lidl", "Løg 1 kg", "ONION", 1000, "g", "10.00"),
    _o("l10", "lidl", "Kidneybønner 400 g", "BEANS_CANNED", 400, "g", "7.00"),
    _o("l11", "lidl", "Lidl Plus: Hakket svinekød 500 g", "PORK_MINCED", 500, "g", "39.00", "25.00", member_only=True, required_membership="lidl_plus"),
    _o("l12", "lidl", "Madlavningsfløde 250 ml", "CREAM", 250, "ml", "12.00"),
    _o("l13", "lidl", "Æg 10 stk", "EGGS", 10, "stk", "28.00"),
    _o("l14", "lidl", "Tortillas 8 stk", "TORTILLA", 8, "stk", "13.00"),
    _o("l15", "lidl", "Kokosmælk 400 ml", "COCONUT_MILK", 400, "ml", "12.00"),
    _o("l16", "lidl", "Revet ost 200 g", "CHEESE_GRATED", 200, "g", "19.00"),
    # --- NETTO (one store-specific offer, one regional) ---
    _o("n1", "netto", "Hakket oksekød 14-18% 1 kg", "BEEF_MINCED_14_18", 1000, "g", "79.00", "49.00"),
    _o("n2", "netto", "Hel kylling 1,2 kg", "WHOLE_CHICKEN", 1200, "g", "45.00", "35.00"),
    _o("n3", "netto", "Kyllingebryst 600 g", "CHICKEN_BREAST", 600, "g", "55.00", "38.00", scope="STORE", store_id="netto_risskov"),
    _o("n4", "netto", "Broccoli 400 g", "BROCCOLI", 400, "g", "15.00", "10.00", scope="REGIONAL", region="midtjylland"),
    _o("n5", "netto", "Pasta 1 kg", "PASTA", 1000, "g", "16.00"),
    _o("n6", "netto", "Hakkede tomater 400 g", "TOMATO_CANNED", 400, "g", "6.50"),
    _o("n7", "netto", "Tacokrydderi 30 g", "TACO_SPICE", 30, "g", "7.00"),
    _o("n8", "netto", "Æg 10 stk", "EGGS", 10, "stk", "30.00"),
    _o("n9", "netto", "Løg 1 kg", "ONION", 1000, "g", "11.00"),
    _o("n10", "netto", "Grødris 1 kg", "RICE", 1000, "g", "20.00"),
    _o("n11", "netto", "Kartofler 2 kg", "POTATO", 2000, "g", "17.00"),
    _o("n12", "netto", "Kikærter 400 g", "CHICKPEAS_CANNED", 400, "g", "8.00"),
    _o("n13", "netto", "Røde linser 500 g", "LENTILS", 500, "g", "16.00"),
    # OCR-ambiguous offer (price should NOT be used for exact plans)
    _o("n14", "netto", "Laksefilet 400 g", "SALMON_FILLET", 400, "g", "69.00", "39.00", ocr={"offer_price": {"raw_value": "3900", "confidence": 0.55, "source_location": "p2"}}),
]


def _ing(cid, qty, unit, **kw):
    return RecipeIngredient(canonical_ingredient_id=cid, quantity=Decimal(str(qty)), unit=unit, **kw)


RECIPES = [
    Recipe(recipe_id="kylling_karry", name="Kylling i karry med ris", servings=4, prep_minutes=10, cook_minutes=20,
           ingredients=[_ing("CHICKEN_BREAST", 500, Unit.G), _ing("RICE", 300, Unit.G), _ing("COCONUT_MILK", 400, Unit.ML),
                        _ing("CURRY_PASTE", 40, Unit.G), _ing("ONION", 150, Unit.G)],
           cuisine="asian", dish_type="CURRY", carbohydrate="RICE", main_protein="CHICKEN", leftover_friendly=True, child_friendly=True),
    Recipe(recipe_id="spaghetti_bolognese", name="Spaghetti bolognese", servings=4, prep_minutes=10, cook_minutes=35,
           ingredients=[_ing("BEEF_MINCED_8_12", 500, Unit.G, substitution_group="MINCED_MEAT", required_attributes={"fat_percentage_max": 12}),
                        _ing("PASTA", 400, Unit.G), _ing("TOMATO_CANNED", 800, Unit.G), _ing("ONION", 150, Unit.G)],
           cuisine="italian", dish_type="PASTA", carbohydrate="PASTA", main_protein="BEEF", allergens=[Allergen.GLUTEN], leftover_friendly=True, child_friendly=True),
    Recipe(recipe_id="tacos_okse", name="Tacos med oksekød", servings=4, prep_minutes=15, cook_minutes=15,
           ingredients=[_ing("BEEF_MINCED_8_12", 500, Unit.G, substitution_group="MINCED_MEAT"), _ing("TORTILLA", 8, Unit.STK),
                        _ing("TACO_SPICE", 30, Unit.G), _ing("CHEESE_GRATED", 150, Unit.G), _ing("ONION", 100, Unit.G)],
           cuisine="mexican", dish_type="TACOS", carbohydrate="BREAD", main_protein="BEEF", allergens=[Allergen.GLUTEN, Allergen.MILK], child_friendly=True),
    Recipe(recipe_id="laks_kartofler", name="Ovnbagt laks med kartofler og broccoli", servings=4, prep_minutes=10, cook_minutes=25,
           ingredients=[_ing("SALMON_FILLET", 500, Unit.G), _ing("POTATO", 800, Unit.G), _ing("BROCCOLI", 400, Unit.G)],
           cuisine="nordic", dish_type="OVEN", carbohydrate="POTATO", main_protein="FISH", allergens=[Allergen.FISH]),
    Recipe(recipe_id="pasta_broccoli", name="Cremet pasta med broccoli", servings=4, prep_minutes=5, cook_minutes=20,
           ingredients=[_ing("PASTA", 400, Unit.G), _ing("BROCCOLI", 400, Unit.G), _ing("CREAM", 250, Unit.ML), _ing("CHEESE_GRATED", 100, Unit.G)],
           cuisine="italian", dish_type="PASTA", carbohydrate="PASTA", main_protein="VEG", allergens=[Allergen.GLUTEN, Allergen.MILK], child_friendly=True),
    Recipe(recipe_id="kikaerte_curry", name="Kikærtekarry", servings=4, prep_minutes=10, cook_minutes=25,
           ingredients=[_ing("CHICKPEAS_CANNED", 800, Unit.G), _ing("COCONUT_MILK", 400, Unit.ML), _ing("TOMATO_CANNED", 400, Unit.G),
                        _ing("CURRY_PASTE", 30, Unit.G), _ing("RICE", 300, Unit.G), _ing("ONION", 150, Unit.G)],
           cuisine="indian", dish_type="CURRY", carbohydrate="RICE", main_protein="VEG", leftover_friendly=True),
    Recipe(recipe_id="frikadeller", name="Frikadeller med kartofler", servings=4, prep_minutes=15, cook_minutes=25,
           ingredients=[_ing("PORK_MINCED", 500, Unit.G), _ing("EGGS", 1, Unit.STK), _ing("ONION", 100, Unit.G), _ing("POTATO", 800, Unit.G)],
           cuisine="danish", dish_type="PAN", carbohydrate="POTATO", main_protein="PORK", allergens=[Allergen.EGG], child_friendly=True),
    Recipe(recipe_id="omelet", name="Omelet med peberfrugt og ost", servings=4, prep_minutes=5, cook_minutes=15,
           ingredients=[_ing("EGGS", 8, Unit.STK), _ing("BELL_PEPPER", 300, Unit.G), _ing("CHEESE_GRATED", 100, Unit.G), _ing("ONION", 100, Unit.G)],
           cuisine="french", dish_type="PAN", carbohydrate="NONE", main_protein="VEG", allergens=[Allergen.EGG, Allergen.MILK], child_friendly=True),
    Recipe(recipe_id="linsesuppe", name="Linsesuppe", servings=4, prep_minutes=10, cook_minutes=30,
           ingredients=[_ing("LENTILS", 300, Unit.G), _ing("TOMATO_CANNED", 400, Unit.G), _ing("ONION", 150, Unit.G), _ing("POTATO", 400, Unit.G)],
           cuisine="middle_eastern", dish_type="SOUP", carbohydrate="POTATO", main_protein="VEG", leftover_friendly=True),
    Recipe(recipe_id="chili_con_carne", name="Chili con carne", servings=4, prep_minutes=10, cook_minutes=40,
           ingredients=[_ing("BEEF_MINCED_8_12", 500, Unit.G, substitution_group="MINCED_MEAT"), _ing("BEANS_CANNED", 400, Unit.G),
                        _ing("TOMATO_CANNED", 800, Unit.G), _ing("ONION", 150, Unit.G), _ing("RICE", 300, Unit.G)],
           cuisine="mexican", dish_type="STEW", carbohydrate="RICE", main_protein="BEEF", leftover_friendly=True),
    Recipe(recipe_id="kylling_broccoli_wok", name="Kyllingewok med broccoli og ris", servings=4, prep_minutes=10, cook_minutes=15,
           ingredients=[_ing("CHICKEN_BREAST", 400, Unit.G), _ing("BROCCOLI", 400, Unit.G), _ing("BELL_PEPPER", 150, Unit.G), _ing("RICE", 300, Unit.G)],
           cuisine="asian", dish_type="WOK", carbohydrate="RICE", main_protein="CHICKEN", child_friendly=True),
    Recipe(recipe_id="kartoffel_omelet", name="Spansk kartoffelomelet", servings=4, prep_minutes=10, cook_minutes=25,
           ingredients=[_ing("EGGS", 6, Unit.STK), _ing("POTATO", 600, Unit.G), _ing("ONION", 150, Unit.G)],
           cuisine="spanish", dish_type="PAN", carbohydrate="POTATO", main_protein="VEG", allergens=[Allergen.EGG]),
]

HOUSEHOLD = Household(
    household_id="hh_demo", name="Familien Demo",
    members=[HouseholdMember(role="adult"), HouseholdMember(role="adult"), HouseholdMember(role="child")],
    location=Location(postal_code="8200", city="Aarhus N"),
    preferences=Preferences(liked_cuisines=["italian", "asian"], favorite_recipes=["kylling_karry"],
                            recipe_ratings={"spaghetti_bolognese": 5, "linsesuppe": 2}, child_friendly=True),
    memberships=[],  # no Lidl Plus -> member-only pork offer must not be used
)

PANTRY = [
    InventoryLot(lot_id="lot_rice", household_id="hh_demo", canonical_product_id="RICE", quantity=Decimal(1000), unit=Unit.G,
                 purchase_date=date(2026, 9, 20), state=InventoryState.CONFIRMED, source=InventorySource.MANUAL, storage=StorageType.AMBIENT),
    InventoryLot(lot_id="lot_onion", household_id="hh_demo", canonical_product_id="ONION", quantity=Decimal(500), unit=Unit.G,
                 purchase_date=date(2026, 9, 28), state=InventoryState.CONFIRMED, source=InventorySource.MANUAL),
    InventoryLot(lot_id="lot_curry", household_id="hh_demo", canonical_product_id="CURRY_PASTE", quantity=Decimal(100), unit=Unit.G,
                 state=InventoryState.CONFIRMED, source=InventorySource.MANUAL),
    InventoryLot(lot_id="lot_pasta_stale", household_id="hh_demo", canonical_product_id="PASTA", quantity=Decimal(500), unit=Unit.G,
                 state=InventoryState.STALE, source=InventorySource.MANUAL),
]


def adapters():
    from hjemmefra.ingestion.adapters.manual_json import ManualJsonAdapter
    by_retailer = {}
    for r in RAW_OFFERS:
        by_retailer.setdefault(r["retailer"], []).append(r)
    return [ManualJsonAdapter(SOURCES[k], records=v, captured_at=CAPTURED_AT) for k, v in sorted(by_retailer.items())]


def load_planning_data(pantry_version: int = 1):
    from hjemmefra.catalog.resolver import ProductResolver
    from hjemmefra.ingestion.pipeline import run_ingestion
    from hjemmefra.planning.service import PlanningData

    resolver = ProductResolver(PRODUCTS, NEGATIVE_ALIASES)
    report = run_ingestion(adapters(), resolver=resolver, known_store_ids={s.store_id for s in STORES}, now=CAPTURED_AT)
    return PlanningData(household=HOUSEHOLD.model_copy(deep=True), stores=STORES, offers=report.offers, products=dict(PRODUCT_MAP),
                        recipes=RECIPES, pantry_lots=[l.model_copy() for l in PANTRY], pantry_version=pantry_version,
                        coverage_warnings=report.coverage_warnings), report
