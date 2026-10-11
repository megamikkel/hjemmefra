import pytest

from hjemmefra.core.metrics import registry
from hjemmefra.demo.dataset import WEEK_START, load_planning_data
from hjemmefra.domain.plan import OptimizationMode, PlanRequest
from hjemmefra.planning.service import generate_plan


@pytest.fixture(autouse=True)
def _reset_metrics():
    registry.reset()
    yield


@pytest.fixture(scope="session")
def demo_data():
    data, report = load_planning_data()
    return data, report


def make_request(**kw) -> PlanRequest:
    base = dict(household_id="hh_demo", start_date=WEEK_START, days=7, budget_minor=60000, max_stores=3, max_distance_km=15,
                optimization_modes=[OptimizationMode.CHEAPEST, OptimizationMode.BALANCED, OptimizationMode.ONE_STORE],
                time_limit_seconds=20)
    base.update(kw)
    return PlanRequest(**base)


@pytest.fixture(scope="session")
def golden_plan(demo_data):
    data, _ = demo_data
    return generate_plan(make_request(), data)
