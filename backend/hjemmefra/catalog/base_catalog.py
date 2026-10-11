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
    _p("TOMATO_PASTE", "Tomatpuré", "canned", Unit.G, ["tomatpuré", "koncentreret tomatpuré", "tomatkoncentrat", "tomat pasta", "tomatpasta"], 365, A, vegan=True, density=1.1),
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
G, M, L, E, N, SE, MU, SO, F, CE = (Allergen.GLUTEN, Allergen.MILK, Allergen.LACTOSE, Allergen.EGG, Allergen.NUTS, Allergen.SESAME,
                                    Allergen.MUSTARD, Allergen.SOY, Allergen.FISH, Allergen.CELERY)
PURCHASABLE += [
    _p("LEMON", "Citron", "fruit", Unit.G, ["citron", "citroner", "øko citron", "økologisk citron", "citronsaft", "saft af citron"], 21, A, vegan=True, piece=120, density=1.0),
    _p("ORANGE", "Appelsin", "fruit", Unit.G, ["appelsin", "appelsiner", "øko appelsin"], 21, A, vegan=True, piece=200),
    _p("YEAST", "Gær", "baking", Unit.G, ["gær", "frisk gær", "tørgær"], 21, vegan=True, piece=50),
    _p("HONEY", "Honning", "baking", Unit.G, ["honning", "flydende honning"], 365, A, density=1.4),
    _p("WHOLEWHEAT_FLOUR", "Fuldkornshvedemel", "dry", Unit.G, ["fuldkornshvedemel", "groft hvedemel", "fuldkorn ølandshvedemel", "ølandshvedemel"], 365, A, allergens=[G], vegan=True, density=0.55),
    _p("MUSTARD", "Sennep", "condiments", Unit.G, ["dijon sennep", "dijonsennep", "grov sennep", "sennep"], 180, A, allergens=[MU], vegan=True, density=1.05),
    _p("GINGER", "Ingefær", "vegetables", Unit.G, ["ingefær", "frisk ingefær"], 21, A, vegan=True, piece=30, density=0.6),
    _p("SESAME_SEEDS", "Sesamfrø", "dry", Unit.G, ["sesamfrø", "sesam"], 365, A, allergens=[SE], vegan=True, density=0.6),
    _p("TAHINI", "Tahin", "condiments", Unit.G, ["tahin", "tahini", "sesampasta"], 365, A, allergens=[SE], vegan=True, density=1.0),
    _p("PINE_NUTS", "Pinjekerner", "dry", Unit.G, ["pinjekerner"], 180, A, allergens=[N], vegan=True, density=0.55),
    _p("ALMONDS", "Mandler", "dry", Unit.G, ["mandler", "hakkede mandler", "mandelflager"], 365, A, allergens=[N], vegan=True, density=0.5),
    _p("HAZELNUTS", "Hasselnødder", "dry", Unit.G, ["hasselnødder", "hasselnøddekerner"], 365, A, allergens=[N], vegan=True, density=0.5),
    _p("WALNUTS", "Valnødder", "dry", Unit.G, ["valnødder", "valnøddekerner"], 365, A, allergens=[N], vegan=True, density=0.4),
    _p("PUMPKIN_SEEDS", "Græskarkerner", "dry", Unit.G, ["græskarkerner"], 365, A, vegan=True, density=0.5),
    _p("SUNFLOWER_SEEDS", "Solsikkekerner", "dry", Unit.G, ["solsikkekerner"], 365, A, vegan=True, density=0.5),
    _p("CUCUMBER", "Agurk", "vegetables", Unit.G, ["agurk", "agurker", "snackagurker"], 7, vegan=True, piece=350),
    _p("TOMATO", "Tomater", "vegetables", Unit.G, ["tomater", "tomat", "blommetomater", "cocktailtomater", "cherrytomater", "snacktomater"], 7, vegan=True, piece=100),
    _p("SPINACH", "Spinat", "vegetables", Unit.G, ["spinat", "baby spinat", "babyspinat", "frisk spinat"], 4, vegan=True),
    _p("FROZEN_SPINACH", "Frossen spinat", "frozen", Unit.G, ["frossen spinat", "hakket spinat"], 365, StorageType.FROZEN, vegan=True),
    _p("MAYONNAISE", "Mayonnaise", "condiments", Unit.G, ["mayonnaise", "mayo"], 90, A, allergens=[E], density=0.95),
    _p("FETA", "Feta", "dairy", Unit.G, ["feta", "fetaost", "salattern"], 30, allergens=[M]),
    _p("YOGURT", "Yoghurt", "dairy", Unit.G, ["yoghurt naturel", "yoghurt", "græsk yoghurt", "skyr"], 14, allergens=[M, L], density=1.05, piece=1000),
    _p("BUTTERMILK", "Kærnemælk", "dairy", Unit.ML, ["kærnemælk"], 10, allergens=[M, L], density=1.03),
    _p("CREAM_CHEESE", "Flødeost", "dairy", Unit.G, ["naturel flødeost", "flødeost", "hvidløgsflødeost", "philadelphia"], 21, allergens=[M, L], density=1.0),
    _p("HALLOUMI", "Halloumi", "dairy", Unit.G, ["halloumi", "grilloumi"], 30, allergens=[M], piece=200, protein="DAIRY"),
    _p("BURRATA", "Burrata", "dairy", Unit.G, ["burrata"], 7, allergens=[M], piece=125),
    _p("SPRING_ONION", "Forårsløg", "vegetables", Unit.G, ["forårsløg"], 7, vegan=True, piece=20),
    _p("LEEK", "Porre", "vegetables", Unit.G, ["porre", "porrer"], 14, vegan=True, piece=250),
    _p("POINTED_CABBAGE", "Spidskål", "vegetables", Unit.G, ["spidskål", "hvidkål"], 14, vegan=True, piece=800),
    _p("KALE", "Grønkål", "vegetables", Unit.G, ["grønkål"], 7, vegan=True),
    _p("RED_CABBAGE", "Rødkål", "vegetables", Unit.G, ["rødkål"], 21, vegan=True, piece=1000),
    _p("CAULIFLOWER", "Blomkål", "vegetables", Unit.G, ["blomkål"], 7, vegan=True, piece=700),
    _p("MUSHROOM", "Champignon", "vegetables", Unit.G, ["champignon", "champignoner", "svampe"], 7, vegan=True, piece=20),
    _p("EGGPLANT", "Aubergine", "vegetables", Unit.G, ["aubergine", "auberginer"], 7, vegan=True, piece=300),
    _p("BEETROOT", "Rødbeder", "vegetables", Unit.G, ["rødbeder", "rødbede"], 21, vegan=True, piece=120),
    _p("PUMPKIN", "Græskar", "vegetables", Unit.G, ["hokkaido græskar", "græskar", "butternut squash"], 30, A, vegan=True, piece=1200),
    _p("PEAS_FROZEN", "Ærter", "frozen", Unit.G, ["frosne ærter", "ærter", "grønne ærter"], 365, StorageType.FROZEN, vegan=True, density=0.65),
    _p("EDAMAME", "Edamamebønner", "frozen", Unit.G, ["edamamebønner", "pillede edamamebønner", "edamame"], 365, StorageType.FROZEN, allergens=[SO], vegan=True, protein="VEG"),
    _p("ASPARAGUS", "Grønne asparges", "vegetables", Unit.G, ["grønne asparges", "asparges"], 4, vegan=True, piece=20),
    _p("SALAD_MIX", "Salat", "vegetables", Unit.G, ["blandet salat", "salat", "hjertesalat", "feldsalat", "iceberg"], 5, vegan=True, piece=200),
    _p("CORN_COB", "Majskolbe", "vegetables", Unit.G, ["majskolbe", "majskolber"], 7, vegan=True, piece=250),
    _p("BREADCRUMBS", "Rasp", "dry", Unit.G, ["rasp", "pankorasp", "panko"], 365, A, allergens=[G], vegan=True, density=0.4),
    _p("BULGUR", "Bulgur", "dry", Unit.G, ["bulgur"], 365, A, allergens=[G], vegan=True, density=0.7),
    _p("RYE_BREAD", "Rugbrød", "bread", Unit.G, ["rugbrød", "skiver rugbrød"], 7, A, allergens=[G], vegan=True, piece=50),
    _p("PITA", "Pitabrød", "bread", Unit.STK, ["pitabrød", "pitabrød fuldkorn"], 7, A, allergens=[G], vegan=True),
    _p("BAKING_POWDER", "Bagepulver", "baking", Unit.G, ["bagepulver", "natron"], 365, A, vegan=True, density=0.9),
    _p("ICING_SUGAR", "Flormelis", "baking", Unit.G, ["flormelis"], 365, A, vegan=True, density=0.55),
    _p("VANILLA_SUGAR", "Vaniljesukker", "baking", Unit.G, ["vaniljesukker"], 365, A, vegan=True, density=0.85),
    _p("CORNSTARCH", "Majsstivelse", "baking", Unit.G, ["majsstivelse", "maizena"], 365, A, vegan=True, density=0.55),
    _p("TUNA", "Tun", "fish", Unit.G, ["tun i vand", "tun i olie", "tun", "tunfisk", "yellowfin tun i vand"], 730, A, protein="FISH", allergens=[F], veg=False, piece=140),
    _p("CHORIZO", "Chorizo", "meat", Unit.G, ["chorizo"], 30, protein="PORK", veg=False),
    _p("PARMA_HAM", "Skinke", "meat", Unit.G, ["parmaskinke", "serranoskinke", "kogt skinke", "hamburgerryg"], 14, protein="PORK", veg=False),
    _p("CHICKEN_MINCED", "Hakket kylling", "meat", Unit.G, ["hakket kylling", "hakket kyllingekød"], 3, protein="CHICKEN", veg=False),
    _p("PORK_VEAL_MINCED", "Hakket grise- og kalvekød", "meat", Unit.G, ["hakket grise- og kalvekød", "hakket kalv og flæsk", "hakket svine- og kalvekød"], 3, protein="PORK", veg=False),
    _p("PESTO", "Pesto", "condiments", Unit.G, ["pesto", "grøn pesto", "rød pesto"], 30, allergens=[M, N], density=1.0),
    _p("KETCHUP", "Ketchup", "condiments", Unit.G, ["ketchup"], 180, A, vegan=True, density=1.1),
    _p("WHITE_WINE", "Hvidvin", "beverages", Unit.ML, ["hvidvin"], 365, A, vegan=True),
    _p("FRYING_OIL", "Fritureolie", "oil", Unit.ML, ["fritureolie", "solsikkeolie", "olie til fritering"], 365, A, vegan=True, density=0.92),
    _p("LUMPFISH_ROE", "Stenbiderrogn", "fish", Unit.G, ["stenbiderrogn", "rogn"], 14, allergens=[F], veg=False),
    _p("DATES", "Dadler", "dry", Unit.G, ["dadler", "medjooldadler"], 180, A, vegan=True, piece=8),
    _p("OLIVES", "Oliven", "canned", Unit.G, ["oliven", "grønne oliven", "sorte oliven", "kalamataoliven"], 180, A, vegan=True),
    _p("CAPERS", "Kapers", "canned", Unit.G, ["kapers"], 365, A, vegan=True, density=0.7),
]
EXTRA_STAPLE_ALIASES = {
    "SALT_PEPPER": ["flagesalt", "groft salt", "havsalt", "hvid peber", "peber efter smag", "sort peber", "peberkorn", "salt m jod"],
    "COOKING_OIL": ["stegeolie", "sesamolie", "smør og olie til stegning", "olie til stegning"],
    "CONDIMENTS": ["æblecidereddike", "riseddike", "hvidvinseddike", "teriyakisauce", "fiskesauce", "worcestershire sauce", "tabasco"],
    "DRIED_SPICES": ["fennikelfrø", "tørret rosmarin", "stødt kardemomme", "stødt nellike", "stødt nelliker", "stødt ingefær", "stødt allehånde",
                     "kardemomme", "nelliker", "allehånde", "gurkemeje", "garam masala", "chilipulver", "cayennepeber", "hvidløgspulver", "løgpulver",
                     "tørret basilikum", "tørret dild", "herbes de provence", "italiensk krydderi"],
}
WATER = _p("WATER", "Vand", "staples", Unit.ML, ["vand", "koldt vand", "kogende vand", "lunkent vand", "stuetempereret vand", "isterninger", "isvand", "vand fra hanen"],
           None, A, vegan=True, staple=True, density=1.0, piece=1)

GARNISH = [
    _p("FRESH_HERBS", "Friske krydderurter", "herbs", Unit.G, ["frisk koriander", "frisk basilikum", "bredbladet persille", "persille", "basilikum",
       "frisk persille", "purløg", "dild", "frisk dild", "frisk mynte", "mynte", "frisk rosmarin", "rosmarin", "frisk timian", "frisk estragon",
       "estragon", "håndfulde frisk mynte", "ramsløg", "karse", "koriander", "frisk oregano", "salvie", "frisk salvie"], 5, vegan=True, garnish=True),
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
STAPLES = [st.model_copy(update={"aliases": list(dict.fromkeys([*st.aliases, *EXTRA_STAPLE_ALIASES.get(st.canonical_id, [])]))}) for st in STAPLES] + [WATER]
BASE_PRODUCTS = PURCHASABLE + GARNISH + STAPLES

# Aliases added to the demo catalog's existing products (the demo products stay the canonical ids).
EXTRA_ALIASES = {
    "PASTA": ["spaghetti", "pasta"],
    "RICE": ["ris", "basmati ris", "basmatiris", "jasmin ris"],
    "TOMATO_CANNED": ["hakkede tomater på dåse"],
    "BEANS_CANNED": ["kidneybønner", "dåser kidneybønner", "sorte bønner"],
    "TORTILLA": ["tortillas pandekager", "tortillas", "tortillapandekager"],
    "CHICKEN_BREAST": ["kyllingebryst", "kyllingebrystfileter"],
    "ONION": ["løg", "rødløg", "skalotteløg", "zittauerløg", "gule løg"],
    "BELL_PEPPER": ["peberfrugt", "peberfrugter", "rød peber", "snack peber", "spidspeber", "rød peberfrugt", "gul peberfrugt"],
    "POTATO": ["babykartofler", "kartofler", "nye kartofler", "bagekartofler", "melede kartofler"],
    "CREAM": ["piskefløde", "fløde", "madlavningsfløde", "kaffefløde"],
    "CHICKPEAS_CANNED": ["kikærter", "dåser kikærter"],
    "CHEESE_GRATED": ["revet ost", "revet mozzarella", "revet pizzaost", "revet parmesan"],
}
# Protein groups for demo products that the demo catalog leaves unset.
DEMO_PROTEIN = {"EGGS": "EGG"}
EGG_GRAMS = 55  # one egg ~ 55 g edible, for the main-meal protein threshold only

# Recipe-level piece/density estimates for demo products (ESTIMATES, conversion only).
DEMO_PIECE_ESTIMATES = {"ONION": 150, "BELL_PEPPER": 150, "BROCCOLI": 400, "BEANS_CANNED": 400, "TOMATO_CANNED": 400, "COCONUT_MILK": 400,
                        "CHICKPEAS_CANNED": 400, "CREAM": 250, "POTATO": 150, "CARROT": 75}
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
        if p.canonical_id in DEMO_PROTEIN and p.protein_group is None:
            upd["protein_group"] = DEMO_PROTEIN[p.canonical_id]
        if p.canonical_id in DEMO_DENSITY_ESTIMATES and p.density_g_per_ml is None:
            upd["density_g_per_ml"] = Decimal(DEMO_DENSITY_ESTIMATES[p.canonical_id])
        out.append(p.model_copy(update=upd) if upd else p)
    known = {p.canonical_id for p in out}
    return out + [p for p in BASE_PRODUCTS if p.canonical_id not in known]
