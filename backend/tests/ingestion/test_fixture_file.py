from pathlib import Path

from hjemmefra.catalog.resolver import ProductResolver
from hjemmefra.demo.dataset import PRODUCTS, RAW_OFFERS, SOURCES
from hjemmefra.ingestion.adapters.manual_json import ManualJsonAdapter
from hjemmefra.ingestion.pipeline import run_ingestion

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "demo_offers.json"


def test_fixture_file_loads_through_adapter():
    adapter = ManualJsonAdapter(SOURCES["rema"], path=FIXTURE)
    report = run_ingestion([adapter], resolver=ProductResolver(PRODUCTS))
    assert len(report.offers) == len(RAW_OFFERS)
    assert all(o.source_reference.endswith("demo_offers.json") for o in report.offers)


def test_missing_fixture_is_reported_not_raised(tmp_path):
    adapter = ManualJsonAdapter(SOURCES["rema"], path=tmp_path / "nope.json")
    report = run_ingestion([adapter], resolver=ProductResolver(PRODUCTS))
    assert "demo_rema" in report.failed_sources and report.offers == []
