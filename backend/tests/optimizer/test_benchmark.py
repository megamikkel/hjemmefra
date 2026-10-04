"""Performance guard: candidate pruning keeps the CP-SAT model small enough to prove
optimality on the demo dataset well inside the time limit (requirement 27)."""
import time

from hjemmefra.core.metrics import OPTIMIZER_RUNTIME, registry
from hjemmefra.domain.plan import OptimizationMode, OptimizationStatus
from hjemmefra.planning.service import generate_plan
from tests.conftest import make_request


def test_seven_day_balanced_under_budget_of_seconds(demo_data):
    data, _ = demo_data
    t0 = time.perf_counter()
    plan = generate_plan(make_request(optimization_modes=[OptimizationMode.BALANCED], time_limit_seconds=30), data)
    elapsed = time.perf_counter() - t0
    sc = plan.scenarios[0]
    assert sc.optimization_status == OptimizationStatus.OPTIMAL
    assert elapsed < 20, f"planning took {elapsed:.1f}s"
    snap = registry.snapshot()["histograms"][OPTIMIZER_RUNTIME]
    assert any(v["count"] >= 1 for v in snap.values())


def test_candidate_pruning_respects_limit(demo_data):
    data, _ = demo_data
    from hjemmefra.optimization.context import OptimizationContext  # noqa: F401
    plan = generate_plan(make_request(optimization_modes=[OptimizationMode.CHEAPEST], days=3, candidate_limit_per_day=5, time_limit_seconds=10), data)
    assert plan.scenarios[0].status.value == "OK"
    assert len({m.recipe_id for m in plan.scenarios[0].meals}) <= 5
