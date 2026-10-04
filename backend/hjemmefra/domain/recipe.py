from __future__ import annotations

from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field

from hjemmefra.core.units import Unit
from hjemmefra.domain.household import Allergen, DietType


class RecipeIngredient(BaseModel):
    canonical_ingredient_id: str
    quantity: Decimal
    unit: Unit
    optional: bool = False
    substitution_group: Optional[str] = None
    required_attributes: dict = Field(default_factory=dict)  # e.g. {"fat_percentage_max": 12}
    accepts_frozen: bool = True
    note: Optional[str] = None


class Recipe(BaseModel):
    recipe_id: str
    name: str
    servings: int
    ingredients: List[RecipeIngredient]
    instructions: List[str] = Field(default_factory=list)
    prep_minutes: int = 0
    cook_minutes: int = 0
    equipment: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    cuisine: Optional[str] = None
    dish_type: Optional[str] = None  # e.g. PASTA, STEW, SOUP, BOWL
    carbohydrate: Optional[str] = None  # PASTA, RICE, POTATO, BREAD, NONE
    main_protein: Optional[str] = None  # CHICKEN, BEEF, PORK, FISH, VEG
    dietary_tags: List[DietType] = Field(default_factory=list)
    allergens: List[Allergen] = Field(default_factory=list)
    freezer_friendly: bool = False
    leftover_friendly: bool = False
    child_friendly: Optional[bool] = None
    nutrition: Optional[dict] = None  # only when reliable; carries source
    nutrition_source: Optional[str] = None
    source: Optional[str] = None
    version: int = 1

    @property
    def total_minutes(self) -> int:
        return self.prep_minutes + self.cook_minutes
