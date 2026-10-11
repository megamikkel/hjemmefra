"""Recipe import from web pages that publish schema.org/Recipe JSON-LD.

Compliance: PUBLIC_PAGE, single URLs supplied by a user/admin (no crawling). Only
the structured JSON-LD block is used and the source URL is stored as provenance.
Ingredient lines are parsed deterministically and resolved against the canonical
catalog; recipes with unresolved required ingredients are stored with
review_required=True and are excluded from planning until an admin maps them.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Tuple

from hjemmefra.catalog.resolver import ProductResolver
from hjemmefra.core.confidence import MatchConfidence
from hjemmefra.core.ids import stable_hash
from hjemmefra.core.units import Unit, UnknownUnit, parse_unit
from hjemmefra.domain.recipe import Recipe, RecipeIngredient
from hjemmefra.ingestion.http import http_get_text

_LD = re.compile(r'<script[^>]*type\s*=\s*["\']?application/ld\+json["\']?[^>]*>(.*?)</script>', re.S | re.I)
_MD_ING = re.compile(r'itemprop\s*=\s*["\']recipeIngredient["\'][^>]*>(.*?)</(?:li|span|div|p|td)>', re.S | re.I)
_MD_NAME = re.compile(r'<h1[^>]*>(.*?)</h1>', re.S | re.I)
_TAGS = re.compile(r"<[^>]+>")
_DUR = re.compile(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?")
_QTY = re.compile(r"^\s*(\d+\s*[½¼¾]|\d+(?:[.,]\d+)?|\d+\s*/\s*\d+|½|¼|¾)\s*(?:(kg|g|gram|ml|cl|dl|l|liter|stk|spsk|tsk|dåse|dåser|pk|pakke|fed|bundt|håndfuld|håndfulde|knivspids|stængler|stængel|dryp|skiver|skive|bæger|bægre|pose|poser|net)\.?(?=\s|$))?\s*(.*)$", re.I)
_FRACTIONS = {"½": Decimal("0.5"), "¼": Decimal("0.25"), "¾": Decimal("0.75")}
# container words -> approximate base quantities only when the word itself carries the size; otherwise unknown
_NON_UNIT_WORDS = {"dåse", "dåser", "fed", "bundt", "håndfuld", "håndfulde", "knivspids", "stængler", "stængel", "dryp", "skiver", "skive",
                   "bæger", "bægre", "pose", "poser", "net"}
_PIECE_WORDS = {"dåse", "dåser", "fed", "stængler", "stængel", "bæger", "bægre", "skiver", "skive"}  # one piece_size_estimate each


@dataclass
class ParsedLine:
    raw: str
    quantity: Optional[Decimal]
    unit: Optional[Unit]
    name: str
    note: Optional[str] = None


@dataclass
class ImportResult:
    recipe: Optional[Recipe]
    review_items: List[dict] = field(default_factory=list)
    error: Optional[str] = None


def parse_ingredient_line(line: str) -> ParsedLine:
    m = _QTY.match(line.strip())
    if not m:
        return ParsedLine(line, None, None, line.strip(), "no quantity")
    q, u, rest = m.group(1), m.group(2), m.group(3)
    if q in _FRACTIONS:
        qty = _FRACTIONS[q]
    elif q[-1] in _FRACTIONS:  # "2½"
        qty = Decimal(q[:-1].strip()) + _FRACTIONS[q[-1]]
    elif "/" in q:
        a, b = q.split("/")
        qty = Decimal(a.strip()) / Decimal(b.strip())
    else:
        qty = Decimal(q.replace(",", "."))
    unit: Optional[Unit] = None
    note = None
    if u:
        ul = u.lower().rstrip(".")
        if ul in _NON_UNIT_WORDS:
            note = f"piece word '{ul}'"
            unit = Unit.STK if ul in _PIECE_WORDS else None
        else:
            try:
                unit = parse_unit(ul)
            except UnknownUnit:
                note = f"unknown unit '{u}'"
    else:
        unit = Unit.STK  # "2 løg" -> 2 stk
    name = re.sub(r"\(.*?\)", "", rest).split(",")[0].strip()
    name = re.sub(r"\s+\d+\s*%$", "", name)  # "cremefraiche 18 %" -> "cremefraiche"
    return ParsedLine(line, qty, unit, name, note)


def _duration_minutes(v: Optional[str]) -> int:
    if not v:
        return 0
    m = _DUR.match(v)
    if not m:
        return 0
    d, h, mi = (int(x) if x else 0 for x in m.groups())
    return d * 1440 + h * 60 + mi


def _find_recipe_node(blocks: List[str]) -> Optional[dict]:
    for b in blocks:
        try:
            data = json.loads(b.strip())
        except json.JSONDecodeError:
            continue
        nodes = data if isinstance(data, list) else [data]
        for n in list(nodes):
            if isinstance(n, dict):
                if isinstance(n.get("@graph"), list):
                    nodes.extend(n["@graph"])
                if isinstance(n.get("mainEntity"), dict):
                    nodes.append(n["mainEntity"])
        for n in nodes:
            t = n.get("@type") if isinstance(n, dict) else None
            if t == "Recipe" or (isinstance(t, list) and "Recipe" in t):
                return n
    return None


_STRIP = re.compile(r"<(style|script|noscript)[^>]*>.*?</\1>", re.S | re.I)
_MD_PROP = re.compile(r'<[^>]*itemprop\s*=\s*["\'](prepTime|cookTime|totalTime|recipeYield)["\'][^>]*>', re.I)
_CONTENT = re.compile(r'(?:content|datetime)\s*=\s*["\']([^"\']+)["\']', re.I)
_ANY_SCRIPT = re.compile(r"<script[^>]*>(.*?)</script>", re.S | re.I)


def _search_recipe(obj, depth: int = 0):
    if depth > 12:
        return None
    if isinstance(obj, dict):
        t = obj.get("@type")
        if (t == "Recipe" or (isinstance(t, list) and "Recipe" in t)) and obj.get("recipeIngredient"):
            return obj
        for v in obj.values():
            r = _search_recipe(v, depth + 1)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _search_recipe(v, depth + 1)
            if r is not None:
                return r
    return None


def _nested_json_recipe(html: str) -> Optional[dict]:
    """Recipes embedded in app state (e.g. Next.js __NEXT_DATA__) rather than a JSON-LD tag."""
    for block in _ANY_SCRIPT.findall(html):
        if '"Recipe"' not in block or "recipeIngredient" not in block:
            continue
        b = block.strip()
        if not b.startswith(("{", "[")):
            continue
        try:
            found = _search_recipe(json.loads(b))
        except json.JSONDecodeError:
            continue
        if found is not None:
            return found
    return None


_LABELLED = {
    "total": re.compile(r"Tid i alt\s*<span[^>]*>([^<]+)</span>", re.I),
    "work": re.compile(r"Arbejdstid\s*<span[^>]*>([^<]+)</span>", re.I),
    "shelf": re.compile(r"Holdbarhed\s*<span[^>]*>([^<]+)</span>", re.I),
    "freeze": re.compile(r"Kan fryses\s*<span[^>]*>([^<]+)</span>", re.I),
}
_MD_TEXT_TIME = re.compile(r'itemprop\s*=\s*["\'](prepTime|cookTime|totalTime)["\'][^>]*>\s*(P[T0-9HMSD]+)\s*<', re.I)


def danish_minutes(text: str) -> Optional[int]:
    """'50 min.' -> 50, '3 timer' -> 180, '1 time og 15 min.' -> 75, '1½ time' -> 90."""
    t = text.lower().replace(",", ".").replace("½", ".5")
    hours = re.search(r"(\d+(?:\.\d+)?)\s*(?:time|timer|t\.)", t)
    mins = re.search(r"(\d+)\s*(?:min|minutter)", t)
    if not hours and not mins:
        return None
    return int(round(float(hours.group(1)) * 60 if hours else 0)) + (int(mins.group(1)) if mins else 0)


def _iso(m: int) -> str:
    return f"PT{m}M"


def _microdata_recipe(html: str) -> Optional[dict]:
    """Fallback for pages that mark ingredients up with schema.org microdata instead of JSON-LD.

    Visible labelled values ("Tid i alt", "Arbejdstid") win over hidden schema tags, which some
    sites fill inconsistently (e.g. cookTime holding the total and totalTime the work time)."""
    times: dict = {}
    for tag in _MD_PROP.finditer(html):
        c = _CONTENT.search(tag.group(0))
        if c:
            times[tag.group(1)] = c.group(1)
    hidden = {k: _duration_minutes(v) for k, v in _MD_TEXT_TIME.findall(html)}
    lab = {k: (rx.search(html).group(1).strip() if rx.search(html) else None) for k, rx in _LABELLED.items()}
    total, work = danish_minutes(lab["total"] or ""), danish_minutes(lab["work"] or "")
    if total is None and hidden:
        vals = [v for v in hidden.values() if v]
        total = max(vals) if vals else None
        work = min(vals) if len(vals) > 1 else work
    if total:
        times["totalTime"] = _iso(total)
        times.pop("cookTime", None)
        if work and work <= total:
            times["prepTime"] = _iso(work)
            times["cookTime"] = _iso(total - work)
    if lab["shelf"]:
        d = re.search(r"(\d+)\s*dag", lab["shelf"].lower())
        if d:
            times["_shelf_life_days"] = int(d.group(1))
    if lab["freeze"]:
        times["_freezable"] = lab["freeze"].strip().lower().startswith("ja")
    y = re.search(r'itemprop\s*=\s*["\']recipeYield["\'][^>]*>\s*(\d+)\s*<', html, re.I)
    if y:
        times["recipeYield"] = y.group(1)
    html = _STRIP.sub("", html)
    ings = [_TAGS.sub("", x).strip() for x in _MD_ING.findall(html)]
    ings = [re.sub(r"\s+", " ", x) for x in ings if x]
    if not ings:
        return None
    m = _MD_NAME.search(html)
    return {"@type": "Recipe", "name": _TAGS.sub("", m.group(1)).strip() if m else "Importeret opskrift",
            "recipeIngredient": ings, "_extracted_from": "microdata", **times}


def extract_recipe_node(html: str) -> Optional[dict]:
    return _find_recipe_node(_LD.findall(html)) or _nested_json_recipe(html) or _microdata_recipe(html)


def _servings(v) -> int:
    if isinstance(v, list):
        v = v[0] if v else None
    m = re.search(r"\d+", str(v or ""))
    return int(m.group()) if m else 4


def recipe_from_jsonld(node: dict, url: str, resolver: ProductResolver) -> ImportResult:
    review: List[dict] = []
    ingredients: List[RecipeIngredient] = []
    needs_review = False
    for line in node.get("recipeIngredient") or []:
        line = re.sub(r"\s+", " ", str(line)).strip()
        if not line or "{" in line or "itemprop" in line:
            continue  # markup/CSS noise
        p = parse_ingredient_line(line)
        match = resolver.resolve(p.name)
        prod = resolver.get(match.canonical_id) if match.canonical_id and match.confidence in (MatchConfidence.HIGH, MatchConfidence.MEDIUM) else None
        if prod is not None and prod.is_staple:
            ingredients.append(RecipeIngredient(canonical_ingredient_id=prod.canonical_id, quantity=p.quantity or Decimal(1),
                                                unit=p.unit or Unit.STK, staple=True, optional=True, note=line))
            continue
        if prod is not None and prod.is_garnish:
            ingredients.append(RecipeIngredient(canonical_ingredient_id=prod.canonical_id, quantity=Decimal(0), unit=prod.base_unit,
                                                optional=True, note=f"{line} (pynt, mængde uoplyst)"))
            continue
        if prod is None or p.quantity is None or p.unit is None:
            needs_review = True
            review.append({"type": "LOW_CONFIDENCE_MATCH" if match.canonical_id else "UNMATCHED_PRODUCT", "source": url,
                           "line": line, "parsed_name": p.name, "canonical_id": match.canonical_id,
                           "confidence": match.confidence.value, "note": p.note})
            ingredients.append(RecipeIngredient(canonical_ingredient_id=f"UNRESOLVED:{stable_hash(p.name.lower())[:8]}",
                                                quantity=p.quantity or Decimal(1), unit=p.unit or Unit.STK, note=line,
                                                unpriced=True, optional=True))
            continue
        qty, unit, est = p.quantity, p.unit, False
        if unit == Unit.STK and prod.base_unit != Unit.STK:
            if prod.piece_size_estimate is None:
                needs_review = True
                review.append({"type": "UNIT_CONVERSION_UNKNOWN", "source": url, "line": line, "canonical_id": prod.canonical_id,
                               "note": f"pieces vs {prod.base_unit.value}; no piece_size_estimate"})
                ingredients.append(RecipeIngredient(canonical_ingredient_id=prod.canonical_id, quantity=qty, unit=unit, note=line,
                                                    unpriced=True, optional=True))
                continue
            else:
                qty, unit, est = qty * prod.piece_size_estimate, prod.base_unit, True
        elif unit.value in ("ml", "cl", "dl", "l", "tsk", "spsk") and prod.base_unit == Unit.G:
            if prod.density_g_per_ml is None:
                needs_review = True
                review.append({"type": "UNIT_CONVERSION_UNKNOWN", "source": url, "line": line, "canonical_id": prod.canonical_id,
                               "note": "volume vs mass; no density"})
                ingredients.append(RecipeIngredient(canonical_ingredient_id=prod.canonical_id, quantity=qty, unit=unit, note=line,
                                                    unpriced=True, optional=True))
                continue
            else:
                est = True  # scale_recipe converts with the documented density estimate
        ingredients.append(RecipeIngredient(canonical_ingredient_id=prod.canonical_id, quantity=qty, unit=unit,
                                            quantity_is_estimate=est, note=line))
    steps = []
    for s in node.get("recipeInstructions") or []:
        if isinstance(s, str):
            steps.append(s)
        elif isinstance(s, dict):
            if s.get("@type") == "HowToSection":
                steps.extend(x.get("text", "") for x in s.get("itemListElement") or [] if isinstance(x, dict))
            else:
                steps.append(s.get("text", ""))
    name = re.sub(r"\s+", " ", str(node.get("name") or "Importeret opskrift")).strip()
    prep, cook, total = (_duration_minutes(node.get(k)) for k in ("prepTime", "cookTime", "totalTime"))
    if total and prep and not cook:
        cook = max(0, total - prep)
    elif total and not prep and not cook:
        prep = total  # only a total is known: count all of it, never less
    time_known = bool(prep or cook or total)
    shelf = node.get("_shelf_life_days")
    main_protein, carb = _infer_main(ingredients, resolver)
    rid = f"web_{stable_hash(url)[:12]}"
    recipe = Recipe(recipe_id=rid, name=name, servings=_servings(node.get("recipeYield")), ingredients=ingredients,
                    instructions=[x for x in steps if x], prep_minutes=prep, cook_minutes=cook, time_known=time_known,
                    main_protein=main_protein, carbohydrate=carb,
                    freezer_friendly=bool(node.get("_freezable")), leftover_friendly=bool(shelf and int(shelf) >= 1),
                    cuisine=(node.get("recipeCuisine") or [None])[0] if isinstance(node.get("recipeCuisine"), list) else node.get("recipeCuisine"),
                    tags=[str(k).strip() for k in str(node.get("keywords") or "").split(",") if k.strip()],
                    source=url, review_required=needs_review)
    return ImportResult(recipe=recipe, review_items=review)


_CARBS = {"PASTA": "PASTA", "LASAGNA_SHEETS": "PASTA", "RICE": "RICE", "POTATO": "POTATO", "TORTILLA": "BREAD", "PITA": "BREAD",
          "RYE_BREAD": "BREAD", "BULGUR": "GRAIN"}


def _grams(i: RecipeIngredient, prod) -> Decimal:
    if prod is None:
        return Decimal(0)
    if i.unit.value == "stk" and prod.canonical_id == "EGGS":
        return i.quantity * 55
    try:
        from hjemmefra.core.units import Quantity
        q = Quantity(i.quantity, i.unit)
        if q.dimension.value == "MASS":
            return q.base_amount()
        if q.dimension.value == "VOLUME" and prod.density_g_per_ml:
            return q.base_amount() * prod.density_g_per_ml
    except Exception:  # noqa: BLE001
        pass
    return Decimal(0)


def _infer_main(ingredients: List[RecipeIngredient], resolver: ProductResolver):
    """Dominant protein group and carbohydrate by mass (deterministic; used for variety, not as a hard fact)."""
    prot: dict = {}
    carb: dict = {}
    for i in ingredients:
        if i.unpriced or i.staple:
            continue
        prod = resolver.get(i.canonical_ingredient_id)
        g = _grams(i, prod)
        if prod is not None and prod.protein_group:
            prot[prod.protein_group] = prot.get(prod.protein_group, 0) + g
        if i.canonical_ingredient_id in _CARBS:
            carb[_CARBS[i.canonical_ingredient_id]] = carb.get(_CARBS[i.canonical_ingredient_id], 0) + g
    mp = max(prot, key=prot.get) if prot else None
    mc = max(carb, key=carb.get) if carb else None
    return mp, mc


def import_recipe_from_url(url: str, resolver: ProductResolver, fetch_text: Callable[..., str] = http_get_text) -> ImportResult:
    try:
        html = fetch_text(url, {"User-Agent": "hjemmefra-recipe-import/0.1 (+structured data only)"})
    except Exception as exc:  # noqa: BLE001
        return ImportResult(None, error=f"{type(exc).__name__}: {exc}")
    node = extract_recipe_node(html)
    if node is None:
        return ImportResult(None, error="no schema.org/Recipe data (JSON-LD or microdata) found on page")
    return recipe_from_jsonld(node, url, resolver)
