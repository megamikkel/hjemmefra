"""Mode -> objective weights. Documented defaults (docs/ARCHITECTURE.md)."""
from __future__ import annotations

from hjemmefra.core.confidence import Confidence
from hjemmefra.domain.plan import BudgetMode, ObjectiveWeights, OptimizationMode, PlanRequest

# Waste penalty in hundredths of øre per base unit (g / ml / stk) of unused purchased food.
# 150 => 1.5 øre/g => 15 kr/kg for highly perishable food.
WASTE_RATE_PERISHABLE = 150
WASTE_RATE_CHILLED = 60
WASTE_RATE_AMBIENT = 10
WASTE_RATE_COUNT = 300  # per piece (e.g. 3 øre per piece... scaled by OBJ_SCALE)
PERISHABLE_SHELF_LIFE_DAYS = 5

OBJ_SCALE = 100  # objective is expressed in hundredths of øre


def weights_for(mode: OptimizationMode, req: PlanRequest) -> tuple[ObjectiveWeights, dict]:
    """Return weights and effective constraint overrides for the mode."""
    w = ObjectiveWeights()
    overrides: dict = {"max_stores": req.max_stores, "budget_mode": req.budget_mode,
                       "min_price_confidence": req.min_price_confidence}
    if mode == OptimizationMode.CHEAPEST:
        w = ObjectiveWeights(travel_cost=0, store_penalty_minor=0, waste_weight=0, preference_weight_minor=0,
                             variety_penalty_minor=500, low_confidence_penalty_minor=0)
        overrides["min_price_confidence"] = Confidence.HIGH  # never chase a LOW-confidence bargain
    elif mode == OptimizationMode.ONE_STORE:
        overrides["max_stores"] = 1
    elif mode == OptimizationMode.BALANCED:
        pass
    elif mode == OptimizationMode.LOW_WASTE:
        w = ObjectiveWeights(waste_weight=5)
    elif mode == OptimizationMode.FAST:
        w = ObjectiveWeights(time_penalty_minor_per_minute=50)
    elif mode == OptimizationMode.FAMILY:
        w = ObjectiveWeights(preference_weight_minor=1000)
    elif mode == OptimizationMode.BUDGET:
        overrides["budget_mode"] = BudgetMode.HARD
    elif mode == OptimizationMode.CUSTOM:
        w = req.custom_weights or ObjectiveWeights()
    return w, overrides
