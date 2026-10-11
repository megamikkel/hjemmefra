"""Base canonical catalog for common Danish home-cooking ingredients (no prices).

piece_size_estimate and density_g_per_ml values are documented ESTIMATES used only to
convert recipe quantities such as "2 løg" or "3 dl ris". They are flagged on every
converted ingredient (quantity_is_estimate) and never used to price anything.
"""
from __future__ import annotations

from decimal import Decimal

from hjemmefra.core.units import Unit
from hjemmefra.domain.household import Allergen
from hjemmefra.domain.product import CanonicalProduct, ProductAttributes, StorageType


def _p(cid, name, cat, unit, aliases=(), shelf=None, storage=StorageType.CHILLED, protein=None, allergens=(), veg=True, vegan=False,
       piece=None, density=None, staple=False, garnish=False):
    return CanonicalProduct(canonical_id=cid, name=name, category=cat, aliases=list(aliases), base_unit=unit,
                            attributes=ProductAttributes(storage=storage, vegetarian=veg, vegan=vegan), allergens=list(allergens),
                            estimated_shelf_life_days=shelf, protein_group=protein,
                            piece_size_estimate=Decimal(str(piece)) if piece is not None else None,
                            density_g_per_ml=Decimal(str(density)) if density is not None else None,
                            is_staple=staple, is_garnish=garnish)


A = StorageType.AMBIENT
PURCHASABLE = [
    _p("BACON", "Bacon", "meat", Unit.G, ["bacon", "baconskiver", "bacon i tern"], 7, protein="PORK", veg=False),
    _p("GARLIC", "Hvidløg", "vegetables", Unit.G, ["hvidløg", "fed hvidløg"], 30, A, vegan=True, piece=5),
    _p("MILK", "Mælk", "dairy", Unit.ML, ["mælk", "letmælk", "sødmælk", "minimælk"], 7, allergens=[Allergen.MILK, Allergen.LACTOSE], density=1.03),
    _p("FLOUR", "Hvedemel", "dry", Unit.G, ["hvedemel", "mel"], 365, A, allergens=[Allergen.GLUTEN], vegan=True, density=0.55),
    _p("BUTTER", "Smør", "dairy", Unit.G, ["smør"], 30, allergens=[Allergen.MILK], density=0.95),
    _p("OATS", "Havregryn", "dry", Unit.G, ["havregryn", "finvalset havregryn", "grovvalset havregryn"], 365, A, allergens=[Allergen.GLUTEN], vegan=True, density=0.35),
    _p("CREME_FRAICHE", "Cremefraiche", "dairy", Unit.ML, ["cremefraiche", "creme fraiche", "cremefraiche 18", "cremefraiche 9"], 14, allergens=[Allergen.MILK, Allergen.LACTOSE], density=1.0),
    _p("CHEDDAR", "Cheddar", "dairy", Unit.G, ["cheddar", "revet cheddar"], 30, allergens=[Allergen.MILK]),
    _p("MOZZARELLA", "Frisk mozzarella", "dairy", Unit.G, ["frisk mozzarella", "mozzarella", "mozzarellakugle"], 10, allergens=[Allergen.MILK], piece=125),
    _p("PARMESAN", "Parmesan", "dairy", Unit.G, ["parmesan", "parmigiano"], 60, allergens=[Allergen.MILK]),
    _p("CARROT", "Gulerødder", "vegetables", Unit.G, ["gulerod", "gulerødder"], 21, vegan=True, piece=75),
    _p("CELERY", "Bladselleri", "vegetables", Unit.G, ["bladselleri", "stængler bladselleri", "stilkselleri"], 10, vegan=True, piece=40, allergens=[Allergen.CELERY]),
    _p("ZUCCHINI", "Squash", "vegetables", Unit.G, ["squash", "courgette"], 7, vegan=True, piece=300),
    _p("TOMATO_PASTE", "Tomatpuré", "canned", Unit.G, ["tomatpuré", "koncentreret tomatpuré", "tomatkoncentrat"], 365, A, vegan=True, density=1.1),
    _p("SUNDRIED_TOMATO", "Soltørrede tomater", "canned", Unit.G, ["soltørrede tomater", "soltørrede tomater i olie"], 180, A, vegan=True, density=0.9),
    _p("LASAGNA_SHEETS", "Lasagneplader", "dry", Unit.G, ["lasagneplader", "lasagneplade"], 365, A, allergens=[Allergen.GLUTEN], vegan=True),
    _p("RED_WINE", "Rødvin", "beverages", Unit.ML, ["rødvin"], 365, A, vegan=True),
    _p("CHOCOLATE_DARK", "Mørk chokolade", "sweets", Unit.G, ["mørk chokolade"], 365, A, allergens=[Allergen.MILK]),
    _p("NACHOS", "Nachos", "snacks", Unit.G, ["nachos", "tortillachips"], 180, A, vegan=True),
    _p("MANGO", "Mango", "fruit", Unit.G, ["mango"], 7, A, vegan=True, piece=350),
    _p("AVOCADO", "Avocado", "fruit", Unit.G, ["avocado", "avocadoer"], 5, A, vegan=True, piece=150),
    _p("LIME", "Lime", "fruit", Unit.STK, ["lime", "øko lime", "limefrugt"], 21, A, vegan=True),
    _p("APPLE", "Æble", "fruit", Unit.G, ["æble", "æbler"], 21, A, vegan=True, piece=150),
    _p("CORN", "Majs", "canned", Unit.G, ["majs", "majskerner"], 730, A, vegan=True),
    _p("RUCOLA", "Rucola", "vegetables", Unit.G, ["rucola", "rucolasalat"], 4, vegan=True),
    _p("CHILI_FRESH", "Rød chili", "vegetables", Unit.G, ["rød chili", "chili", "chilipeber"], 10, vegan=True, piece=15),
]
GARNISH = [
    _p("FRESH_HERBS", "Friske krydderurter", "herbs", Unit.G, ["frisk koriander", "frisk basilikum", "bredbladet persille", "persille", "basilikum", "frisk persille", "purløg", "dild"], 5, vegan=True, garnish=True),
]
STAPLES = [
    _p("SALT_PEPPER", "Salt og peber", "staples", Unit.G, ["salt", "peber", "salt og peber", "salt og friskkværnet peber", "friskkværnet peber", "salt og friskkværnet peber til stegning"], None, A, vegan=True, staple=True, density=1.0, piece=1),
    _p("COOKING_OIL", "Olie", "staples", Unit.ML, ["olivenolie", "olie", "rapsolie", "neutral olie", "olivenolie til stegning"], None, A, vegan=True, staple=True, density=0.92),
    _p("DRIED_SPICES", "Tørrede krydderier", "staples", Unit.G, [
        "tørret timian", "tørret oregano", "stødt spidskommen", "stødt kanel", "stødt koriander", "chiliflager", "sød paprika", "røget paprika",
        "paprika", "karry", "mediumstærk karry", "muskatnød", "knivspids muskatnød", "spidskommen", "kanel", "timian", "oregano", "laurbærblade"],
       None, A, vegan=True, staple=True, density=0.5, piece=1),
    _p("SUGAR", "Sukker", "staples", Unit.G, ["sukker", "brun farin", "rørsukker"], None, A, vegan=True, staple=True, density=0.85),
    _p("BOUILLON", "Bouillon", "staples", Unit.ML, ["bouillon", "grøntsagsbouillon", "oksebouillon", "hønsebouillon", "bouillonterning", "grøntsagsboullion"], None, A, vegan=True, staple=True, density=1.0, piece=500),
    _p("CONDIMENTS", "Basis-saucer", "staples", Unit.ML, ["rød balsamico", "balsamico", "sriracha", "sriracha chilisauce", "soja", "sojasauce", "eddike"], None, A, vegan=True, staple=True, density=1.0),
]
BASE_PRODUCTS = PURCHASABLE + GARNISH + STAPLES

# Aliases added to the demo catalog's existing products (the demo products stay the canonical ids).
EXTRA_ALIASES = {
    "PASTA": ["spaghetti", "pasta"],
    "RICE": ["ris", "basmati ris", "basmatiris", "jasmin ris"],
    "TOMATO_CANNED": ["hakkede tomater på dåse"],
    "BEANS_CANNED": ["kidneybønner", "dåser kidneybønner", "sorte bønner"],
    "TORTILLA": ["tortillas pandekager", "tortillas", "tortillapandekager"],
    "CHICKEN_BREAST": ["kyllingebryst", "kyllingebrystfileter"],
    "ONION": ["løg", "rødløg"],
}
# Recipe-level piece/density estimates for demo products (ESTIMATES, conversion only).
DEMO_PIECE_ESTIMATES = {"ONION": 150, "BELL_PEPPER": 150, "BROCCOLI": 400, "BEANS_CANNED": 400, "TOMATO_CANNED": 400, "COCONUT_MILK": 400}
DEMO_DENSITY_ESTIMATES = {"RICE": "0.85", "PASTA": "0.45", "LENTILS": "0.8", "CHEESE_GRATED": "0.4"}


def merged_catalog(demo_products):
    """Demo products enriched with extra aliases/estimates, plus the base catalog."""
    out = []
    for p in demo_products:
        upd = {}
        if p.canonical_id in EXTRA_ALIASES:
            upd["aliases"] = list(dict.fromkeys([*p.aliases, *EXTRA_ALIASES[p.canonical_id]]))
        if p.canonical_id in DEMO_PIECE_ESTIMATES and p.piece_size_estimate is None:
            upd["piece_size_estimate"] = Decimal(DEMO_PIECE_ESTIMATES[p.canonical_id])
        if p.canonical_id in DEMO_DENSITY_ESTIMATES and p.density_g_per_ml is None:
            upd["density_g_per_ml"] = Decimal(DEMO_DENSITY_ESTIMATES[p.canonical_id])
        out.append(p.model_copy(update=upd) if upd else p)
    known = {p.canonical_id for p in out}
    return out + [p for p in BASE_PRODUCTS if p.canonical_id not in known]
