from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field

from hjemmefra.core.units import Unit
from hjemmefra.domain.household import HouseholdMember, Location, Membership, Preferences
from hjemmefra.domain.pantry import InventoryState, InventorySource
from hjemmefra.domain.plan import BudgetMode, ObjectiveWeights, OptimizationMode
from hjemmefra.domain.product import StorageType


class HouseholdCreate(BaseModel):
    name: str
    members: List[HouseholdMember]
    location: Location
    preferences: Preferences = Field(default_factory=Preferences)
    memberships: List[Membership] = Field(default_factory=list)


class HouseholdCreated(BaseModel):
    household_id: str
    api_key: str  # shown once


class PantryLotCreate(BaseModel):
    canonical_product_id: str
    quantity: Decimal
    unit: Unit
    purchase_date: Optional[date] = None
    expiry_date: Optional[date] = None
    expiry_is_estimate: bool = True
    state: InventoryState = InventoryState.CONFIRMED
    source: InventorySource = InventorySource.MANUAL
    storage: Optional[StorageType] = None
    expected_version: Optional[int] = None


class PlanCreate(BaseModel):
    start_date: date
    days: int = Field(ge=1, le=14, default=7)
    shopping_dates: List[date] = Field(default_factory=list)
    servings_per_meal: Optional[int] = None
    budget_dkk: Optional[Decimal] = None
    budget_mode: BudgetMode = BudgetMode.SOFT
    optimization_modes: List[OptimizationMode] = Field(default_factory=lambda: [OptimizationMode.CHEAPEST, OptimizationMode.BALANCED, OptimizationMode.ONE_STORE])
    custom_weights: Optional[ObjectiveWeights] = None
    max_stores: int = Field(default=2, ge=1, le=6)
    max_distance_km: float = 10.0
    max_prep_minutes: Optional[int] = None
    selected_store_ids: List[str] = Field(default_factory=list)
    pantry_version: Optional[int] = None
    allow_leftover_meals: bool = True
    time_limit_seconds: float = Field(default=10.0, ge=0.5, le=60)
    idempotency_key: Optional[str] = None


class FeedbackCreate(BaseModel):
    recipe_id: str
    kind: str = Field(pattern="^(liked|disliked|too_expensive|too_difficult|too_much_food|too_little_food|would_make_again|skip_recipe)$")
    plan_id: Optional[str] = None
    comment: Optional[str] = None


class OfferImport(BaseModel):
    source_id: str
    retailer: str
    source_type: str = "MANUAL"
    compliance: str = "USER_SUPPLIED"
    records: List[dict]


class ReviewResolve(BaseModel):
    action: str  # e.g. MAP_PRODUCT, ACCEPT, REJECT
    canonical_product_id: Optional[str] = None
    note: Optional[str] = None
