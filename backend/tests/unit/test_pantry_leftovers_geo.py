from datetime import date, timedelta
from decimal import Decimal

import pytest

from hjemmefra.core.units import Unit
from hjemmefra.demo.dataset import HOUSEHOLD, PRODUCT_MAP, STORES
from hjemmefra.domain.pantry import InventoryLot, InventoryState
from hjemmefra.leftovers.engine import LeftoverConflict, LeftoverLedger
from hjemmefra.location.geo import filter_stores
from hjemmefra.pantry.service import allocate, usable_lots


def lot(state, qty=500, expiry=None, cid="RICE"):
    return InventoryLot(lot_id=f"l_{state}_{qty}", household_id="h", canonical_product_id=cid, quantity=Decimal(qty), unit=Unit.G,
                        state=state, expiry_date=expiry)


def test_stale_and_unknown_lots_never_reduce_shopping():
    lots = [lot(InventoryState.STALE), lot(InventoryState.UNKNOWN), lot(InventoryState.CONFIRMED, 200)]
    u = usable_lots(lots, PRODUCT_MAP, date(2026, 10, 5))
    assert sum(x.usable_base_qty for x in u["RICE"]) == 200


def test_expired_lot_excluded_and_fefo_allocation():
    lots = [lot(InventoryState.CONFIRMED, 300, expiry=date(2026, 10, 1)),
            lot(InventoryState.CONFIRMED, 300, expiry=date(2026, 10, 20)),
            lot(InventoryState.ESTIMATED, 300, expiry=date(2026, 10, 8))]
    u = usable_lots(lots, PRODUCT_MAP, date(2026, 10, 5))["RICE"]
    assert [x.lot.expiry_date for x in u] == [date(2026, 10, 8), date(2026, 10, 20)]
    alloc = allocate(u, Decimal(400))
    assert [(a[0].lot.expiry_date, a[1]) for a in alloc] == [(date(2026, 10, 8), Decimal(300)), (date(2026, 10, 20), Decimal(100))]
    assert sum(a[1] for a in alloc) == 400  # never over-allocates


def test_leftover_cannot_be_double_spent():
    led = LeftoverLedger()
    lo = led.produce("kylling", Decimal(250), Unit.G, date(2026, 10, 5), "r")
    led.reserve(lo.leftover_id, date(2026, 10, 6))
    with pytest.raises(LeftoverConflict):
        led.reserve(lo.leftover_id, date(2026, 10, 7))
    led.consume(lo.leftover_id, date(2026, 10, 6))
    with pytest.raises(LeftoverConflict):
        led.consume(lo.leftover_id, date(2026, 10, 6))


def test_leftover_respects_availability_and_expiry():
    led = LeftoverLedger()
    lo = led.produce("x", Decimal(1), Unit.PORTION, date(2026, 10, 5), "r", shelf_life_days=2)
    with pytest.raises(LeftoverConflict):
        led.reserve(lo.leftover_id, date(2026, 10, 5))
    with pytest.raises(LeftoverConflict):
        led.reserve(lo.leftover_id, date(2026, 10, 8))
    assert lo.expiry_is_estimate


def test_store_filter_radius_and_method():
    near = filter_stores(HOUSEHOLD.location, STORES, max_distance_km=5)
    ids = {d.store.store_id for d in near}
    assert "netto_odense" not in ids and "rema_aarhus_n" in ids
    assert all(d.distance_method == "STRAIGHT_LINE_APPROX" for d in near)
    only = filter_stores(HOUSEHOLD.location, STORES, 5, selected_store_ids=["lidl_aarhus_n"])
    assert [d.store.store_id for d in only] == ["lidl_aarhus_n"]
