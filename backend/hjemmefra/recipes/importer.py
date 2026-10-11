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

_LD = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S | re.I)
_DUR = re.compile(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?")
_QTY = re.compile(r"^\s*(\d+(?:[.,]\d+)?|\d+\s*/\s*\d+|½|¼|¾)\s*(?:(kg|g|gram|ml|cl|dl|l|liter|stk|spsk|tsk|dåse|dåser|pk|pakke|fed|bundt)\.?(?=\s|$))?\s*(.*)$", re.I)
_FRACTIONS = {"½": Decimal("0.5"), "¼": Decimal("0.25"), "¾": Decimal("0.75")}
# container words -> approximate base quantities only when the word itself carries the size; otherwise unknown
_NON_UNIT_WORDS = {"dåse", "dåser", "fed", "bundt"}


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
            note = f"container word '{ul}' - package size unknown"
            unit = Unit.STK if ul in ("fed", "bundt") else None
        else:
            try:
                unit = parse_unit(ul)
            except UnknownUnit:
                note = f"unknown unit '{u}'"
    else:
        unit = Unit.STK  # "2 løg" -> 2 stk
    name = re.sub(r"\(.*?\)", "", rest).split(",")[0].strip()
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
            if isinstance(n, dict) and "@graph" in n:
                nodes.extend(n["@graph"])
        for n in nodes:
            t = n.get("@type") if isinstance(n, dict) else None
            if t == "Recipe" or (isinstance(t, list) and "Recipe" in t):
                return n
    return None


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
        p = parse_ingredient_line(str(line))
        match = resolver.resolve(p.name)
        if match.confidence in (MatchConfidence.LOW, MatchConfidence.UNMATCHED) or p.quantity is None or p.unit is None:
            needs_review = True
            review.append({"type": "LOW_CONFIDENCE_MATCH" if match.canonical_id else "UNMATCHED_PRODUCT", "source": url,
                           "line": line, "parsed_name": p.name, "canonical_id": match.canonical_id,
                           "confidence": match.confidence.value, "note": p.note})
        cid = match.canonical_id or f"UNRESOLVED:{stable_hash(p.name)[:8]}"
        prod = resolver.get(cid) if match.canonical_id else None
        unit = p.unit or Unit.STK
        if prod is not None and p.unit is not None and p.unit.value in ("stk",) and prod.base_unit.value != "stk":
            needs_review = True
            review.append({"type": "UNIT_CONVERSION_UNKNOWN", "source": url, "line": line, "canonical_id": cid,
                           "note": f"'{p.unit.value}' vs product base unit {prod.base_unit.value}"})
        ingredients.append(RecipeIngredient(canonical_ingredient_id=cid, quantity=p.quantity or Decimal(1), unit=unit,
                                            note=str(line)))
    steps = []
    for s in node.get("recipeInstructions") or []:
        if isinstance(s, str):
            steps.append(s)
        elif isinstance(s, dict):
            if s.get("@type") == "HowToSection":
                steps.extend(x.get("text", "") for x in s.get("itemListElement") or [] if isinstance(x, dict))
            else:
                steps.append(s.get("text", ""))
    name = str(node.get("name") or "Importeret opskrift")
    rid = f"web_{stable_hash(url)[:12]}"
    recipe = Recipe(recipe_id=rid, name=name, servings=_servings(node.get("recipeYield")), ingredients=ingredients,
                    instructions=[x for x in steps if x], prep_minutes=_duration_minutes(node.get("prepTime")),
                    cook_minutes=_duration_minutes(node.get("cookTime")) or max(0, _duration_minutes(node.get("totalTime")) - _duration_minutes(node.get("prepTime"))),
                    cuisine=(node.get("recipeCuisine") or [None])[0] if isinstance(node.get("recipeCuisine"), list) else node.get("recipeCuisine"),
                    tags=[str(k).strip() for k in str(node.get("keywords") or "").split(",") if k.strip()],
                    source=url, review_required=needs_review)
    return ImportResult(recipe=recipe, review_items=review)


def import_recipe_from_url(url: str, resolver: ProductResolver, fetch_text: Callable[..., str] = http_get_text) -> ImportResult:
    try:
        html = fetch_text(url, {"User-Agent": "hjemmefra-recipe-import/0.1 (+structured data only)"})
    except Exception as exc:  # noqa: BLE001
        return ImportResult(None, error=f"{type(exc).__name__}: {exc}")
    node = _find_recipe_node(_LD.findall(html))
    if node is None:
        return ImportResult(None, error="no schema.org/Recipe JSON-LD found on page")
    return recipe_from_jsonld(node, url, resolver)
