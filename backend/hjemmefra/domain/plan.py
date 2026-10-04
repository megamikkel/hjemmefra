from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from hjemmefra.core.confidence import Confidence
from hjemmefra.core.units import Unit


class OptimizationMode(str, Enum):
    CHEAPEST = "CHEAPEST"
    ONE_STORE = "ONE_STORE"
    BALANCED = "BALANCED"
    LOW_WASTE = "LOW_WASTE"
    FAST = "FAST"
    FAMILY = "FAMILY"
    BUDGET = "BUDGET"
    CUSTOM = "CUSTOM"


class BudgetMode(str, Enum):
    HARD = "HARD"  # must not be exceeded
    SOFT = "SOFT"  # target, penalised when exceeded


class OptimizationStatus(str, Enum):
    OPTIMAL = "OPTIMAL"
    FEASIBLE = "FEASIBLE"
    TIME_LIMIT = "TIME_LIMIT"
    INFEASIBLE = "INFEASIBLE"
    ERROR = "ERROR"


class PlanStatus(str, Enum):
    OK = "OK"
    NO_FEASIBLE_PLAN = "NO_FEASIBLE_PLAN"
    PARTIAL = "PARTIAL"


class Availability(str, Enum):
    OFFERED = "OFFERED"  # in a leaflet/feed; not a stock guarantee
    IN_STOCK = "IN_STOCK"  # only with real-time inventory data
    UNKNOWN = "UNKNOWN"


class ObjectiveWeights(BaseModel):
    """All weights are in øre-equivalents so the objective is a single generalized cost.
    Documented defaults in docs/ARCHITECTURE.md (section Objective)."""
    checkout_cost: int = 1  # multiplier on checkout øre
    travel_cost: int = 1  # multiplier on estimated travel øre
    store_penalty_minor: int = 1500  # øre per store beyond the first (15 kr inconvenience)
    waste_weight: int = 1  # multiplier on waste penalty øre
    preference_weight_minor: int = 300  # øre of value per preference point
    time_penalty_minor_per_minute: int = 0  # øre per minute of total cooking time
    variety_penalty_minor: int = 2000  # øre per same-protein/dish repeat on consecutive days
    low_confidence_penalty_minor: int = 500  # øre per package priced with LOW/MEDIUM confidence
    budget_overrun_weight: int = 3  # SOFT budget: multiplier on overrun øre


class PlanRequest(BaseModel):
    household_id: str
    start_date: date
    days: int = Field(ge=1, le=14)
    shopping_dates: List[date] = Field(default_factory=list)  # defaults to [start_date]
    servings_per_meal: Optional[int] = None
    budget_minor: Optional[int] = None
    budget_mode: BudgetMode = BudgetMode.SOFT
    optimization_modes: List[OptimizationMode] = Field(default_factory=lambda: [OptimizationMode.BALANCED])
    custom_weights: Optional[ObjectiveWeights] = None
    max_stores: int = Field(default=2, ge=1, le=6)
    max_distance_km: float = 10.0
    max_prep_minutes: Optional[int] = None
    selected_store_ids: List[str] = Field(default_factory=list)
    pantry_version: Optional[int] = None
    max_recipe_repeats: int = 1
    candidate_limit_per_day: int = 12
    time_limit_seconds: float = 10.0
    min_price_confidence: Confidence = Confidence.MEDIUM  # exclude lower confidence prices
    allow_leftover_meals: bool = True
    deterministic_seed: int = 0


class PurchaseLine(BaseModel):
    canonical_product_id: str
    product_name: str
    store_id: str
    store_name: str
    offer_id: Optional[str]
    price_source: str  # OFFER | REGULAR_PRICE | UNKNOWN
    packages: int
    package_quantity: Decimal
    package_unit: Unit
    total_quantity: Decimal
    consumed_quantity: Decimal
    remainder_quantity: Decimal
    product_cost_minor: int
    deposit_minor: int
    checkout_cost_minor: int
    consumed_value_minor: int
    reference_cost_minor: Optional[int]
    reference_method: str  # OFFER_STATED_NORMAL | HISTORICAL_MEDIAN | UNKNOWN
    saving_minor: Optional[int]
    saving_confidence: Confidence
    price_confidence: Confidence
    availability: Availability = Availability.OFFERED
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    multi_buy_applied: bool = False
    explanation: str = ""


class PantryUse(BaseModel):
    canonical_product_id: str
    lot_id: str
    quantity: Decimal
    unit: Unit
    state: str


class LeftoverUse(BaseModel):
    leftover_id: str
    description: str
    from_day: date
    used_on: date


class Meal(BaseModel):
    day: date
    recipe_id: str
    recipe_name: str
    servings: int
    is_leftover_meal: bool = False
    cooked_on: Optional[date] = None
    total_minutes: int
    checkout_contribution_minor: int
    reasons: List[str] = Field(default_factory=list)


class StoreBreakdown(BaseModel):
    store_id: str
    store_name: str
    chain_id: str
    lines: List[PurchaseLine]
    subtotal_minor: int
    deposit_minor: int
    checkout_minor: int
    distance_km: Optional[float]
    distance_method: str
    travel_cost_minor: int


class WasteEstimate(BaseModel):
    unused_items: List[dict]
    total_unused_value_minor: int
    reused_in_later_meals_grams: Decimal


class ConfidenceSummary(BaseModel):
    verified_share_of_checkout: Decimal  # 0..1
    verified_total_minor: int
    unverified_total_minor: int
    unknown_price_items: List[str]
    overall: Confidence


class Scenario(BaseModel):
    mode: OptimizationMode
    status: PlanStatus
    optimization_status: OptimizationStatus
    objective_value: Optional[int] = None
    meals: List[Meal] = Field(default_factory=list)
    purchases: List[PurchaseLine] = Field(default_factory=list)
    pantry_uses: List[PantryUse] = Field(default_factory=list)
    leftover_uses: List[LeftoverUse] = Field(default_factory=list)
    store_breakdown: List[StoreBreakdown] = Field(default_factory=list)
    checkout_total_minor: int = 0
    deposit_total_minor: int = 0
    reference_total_minor: Optional[int] = None
    verified_saving_minor: Optional[int] = None
    saving_confidence: Confidence = Confidence.UNKNOWN
    travel_cost_minor: int = 0
    store_penalty_minor: int = 0
    net_saving_vs_one_store_minor: Optional[int] = None
    waste: Optional[WasteEstimate] = None
    confidence: Optional[ConfidenceSummary] = None
    store_count: int = 0
    warnings: List[str] = Field(default_factory=list)
    explanations: List[str] = Field(default_factory=list)
    infeasibility_reason: Optional[str] = None
    minimum_estimated_required_budget_minor: Optional[int] = None
    relaxed_constraints: List[str] = Field(default_factory=list)
    solver_wall_time_seconds: float = 0.0


class DataSnapshot(BaseModel):
    snapshot_id: str
    created_at: datetime
    offer_ids: List[str]
    offer_versions: Dict[str, int]
    recipe_versions: Dict[str, int]
    product_versions: Dict[str, int]
    pantry_version: Optional[int]
    household_version: int
    weights: Dict[str, ObjectiveWeights]


class PlanResult(BaseModel):
    plan_id: str
    household_id: str
    created_at: datetime
    optimizer_version: str
    request: PlanRequest
    data_snapshot: DataSnapshot
    scenarios: List[Scenario]
    coverage_warnings: List[str] = Field(default_factory=list)
