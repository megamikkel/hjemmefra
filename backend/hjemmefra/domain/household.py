from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class DietType(str, Enum):
    OMNIVORE = "OMNIVORE"
    VEGETARIAN = "VEGETARIAN"
    VEGAN = "VEGAN"
    PESCETARIAN = "PESCETARIAN"
    HALAL = "HALAL"
    KOSHER = "KOSHER"
    GLUTEN_FREE = "GLUTEN_FREE"
    LACTOSE_FREE = "LACTOSE_FREE"


class Allergen(str, Enum):
    GLUTEN = "GLUTEN"
    LACTOSE = "LACTOSE"
    MILK = "MILK"
    EGG = "EGG"
    NUTS = "NUTS"
    PEANUTS = "PEANUTS"
    SOY = "SOY"
    FISH = "FISH"
    SHELLFISH = "SHELLFISH"
    SESAME = "SESAME"
    CELERY = "CELERY"
    MUSTARD = "MUSTARD"
    SULPHITES = "SULPHITES"
    LUPIN = "LUPIN"
    MOLLUSCS = "MOLLUSCS"


class Membership(BaseModel):
    program_id: str  # e.g. "coop_medlem", "salling_plus", "lidl_plus"
    has_digital_coupons: bool = False


class HouseholdMember(BaseModel):
    role: str = "adult"  # adult | child
    age_group: Optional[str] = None  # optional, user supplied


class Location(BaseModel):
    """Least-precision-necessary location. Postal code is enough for store filtering
    with centroid lookup; coordinates are optional."""
    postal_code: str
    city: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None


class Preferences(BaseModel):
    # hard constraints
    allergens: List[Allergen] = Field(default_factory=list)
    excluded_ingredients: List[str] = Field(default_factory=list)  # canonical ingredient ids
    diet: Optional[DietType] = None
    max_prep_minutes: Optional[int] = None  # hard if set via request; preference here
    # soft preferences
    liked_ingredients: List[str] = Field(default_factory=list)
    disliked_ingredients: List[str] = Field(default_factory=list)
    liked_cuisines: List[str] = Field(default_factory=list)
    favorite_recipes: List[str] = Field(default_factory=list)
    recipe_ratings: Dict[str, int] = Field(default_factory=dict)  # recipe_id -> 1..5
    recently_eaten: Dict[str, date] = Field(default_factory=dict)  # recipe_id -> date
    less_meat: bool = False
    child_friendly: bool = False
    preferred_store_ids: List[str] = Field(default_factory=list)
    leftover_preference: str = "ALLOW"  # ALLOW | PREFER | AVOID


class Household(BaseModel):
    household_id: str
    name: str
    members: List[HouseholdMember]
    location: Location
    preferences: Preferences = Field(default_factory=Preferences)
    memberships: List[Membership] = Field(default_factory=list)
    version: int = 1

    @property
    def adults(self) -> int:
        return sum(1 for m in self.members if m.role == "adult")

    @property
    def children(self) -> int:
        return sum(1 for m in self.members if m.role == "child")

    def default_servings(self) -> int:
        # Children count as 0.5 adult portion, rounded up; minimum 1.
        from math import ceil
        return max(1, ceil(self.adults + 0.5 * self.children))

    def has_membership(self, program_id: str) -> bool:
        return any(m.program_id == program_id for m in self.memberships)

    def has_coupons(self, program_id: str) -> bool:
        return any(m.program_id == program_id and m.has_digital_coupons for m in self.memberships)
