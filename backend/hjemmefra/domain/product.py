from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from hjemmefra.core.units import Unit
from hjemmefra.domain.household import Allergen


class StorageType(str, Enum):
    FRESH = "FRESH"
    FROZEN = "FROZEN"
    CHILLED = "CHILLED"
    AMBIENT = "AMBIENT"


class ProductAttributes(BaseModel):
    brand: Optional[str] = None
    variant: Optional[str] = None
    fat_percentage: Optional[Decimal] = None
    organic: Optional[bool] = None
    storage: Optional[StorageType] = None
    vegetarian: bool = True
    vegan: bool = False
    halal: Optional[bool] = None
    gluten_free: Optional[bool] = None
    lactose_free: Optional[bool] = None


class CanonicalProduct(BaseModel):
    """Canonical purchasable product / ingredient class, e.g. CHICKEN_BREAST."""
    canonical_id: str
    name: str
    category: str
    subcategory: Optional[str] = None
    aliases: List[str] = Field(default_factory=list)
    attributes: ProductAttributes = Field(default_factory=ProductAttributes)
    allergens: List[Allergen] = Field(default_factory=list)
    base_unit: Unit  # g | ml | stk
    density_g_per_ml: Optional[Decimal] = None  # documented, product specific
    typical_package_min: Optional[Decimal] = None
    typical_package_max: Optional[Decimal] = None
    substitution_group: Optional[str] = None
    protein_group: Optional[str] = None  # e.g. CHICKEN, BEEF, PORK, FISH, VEG
    # conservative estimate of days until spoilage after purchase, by storage
    estimated_shelf_life_days: Optional[int] = None
    # Estimated weight (g) or volume (ml) of one piece/container as a recipe counts it ("2 løg", "1 dåse").
    # Always an ESTIMATE; used only to convert recipe quantities, never to price.
    piece_size_estimate: Optional[Decimal] = None
    is_staple: bool = False  # salt, pepper, oil, dried spices: covered only if the household declares basic staples
    is_garnish: bool = False  # fresh herbs etc.: may be dropped when the recipe gives no measurable quantity
    # waste penalty weight (øre per base unit) when left unused; documented default by category
    version: int = 1
