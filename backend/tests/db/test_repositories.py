from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from hjemmefra.core.errors import ConflictError
from hjemmefra.core.units import Unit
from hjemmefra.demo.dataset import HOUSEHOLD
from hjemmefra.demo.seed import seed_demo
from hjemmefra.domain.pantry import InventoryLot
from hjemmefra.persistence.db import Base, make_engine, make_session_factory
from hjemmefra.persistence.repositories import HouseholdRepo, OfferRepo, PantryRepo


@pytest.fixture()
def session():
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = make_session_factory(engine)()
    yield s
    s.close()


def test_seed_is_idempotent(session):
    a = seed_demo(session)
    session.commit()
    b = seed_demo(session)
    assert a["new_offers"] > 0 and b["new_offers"] == 0 and b["duplicates"] == a["new_offers"]


def test_offer_validity_query(session):
    seed_demo(session)
    repo = OfferRepo(session)
    assert len(repo.valid_on(date(2026, 10, 6))) == len(repo.all())
    assert repo.valid_on(date(2026, 10, 20)) == []
    assert all(o.retailer == "lidl" for o in repo.valid_on(date(2026, 10, 6), ["lidl"]))


def test_optimistic_concurrency(session):
    seed_demo(session)
    hh = HouseholdRepo(session)
    h = hh.get(HOUSEHOLD.household_id)
    hh.save(h, expected_version=h.version)
    with pytest.raises(ConflictError):
        hh.save(h, expected_version=1)
    pantry = PantryRepo(session)
    v = pantry.version(HOUSEHOLD.household_id)
    lot = InventoryLot(lot_id="x", household_id=HOUSEHOLD.household_id, canonical_product_id="EGGS", quantity=Decimal(6), unit=Unit.STK)
    assert pantry.add(lot, expected_version=v) == v + 1
    with pytest.raises(ConflictError):
        pantry.add(lot, expected_version=v)


def test_alembic_migration_matches_models(tmp_path):
    import subprocess, sys, os
    db = tmp_path / "m.db"
    env = {**os.environ, "HJEMMEFRA_DATABASE_URL": f"sqlite:///{db}"}
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True, env=env, cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    engine = make_engine(f"sqlite:///{db}")
    with engine.connect() as c:
        tables = {r[0] for r in c.execute(text("select name from sqlite_master where type='table'"))}
    assert set(Base.metadata.tables) <= tables
