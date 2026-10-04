import pytest
from fastapi.testclient import TestClient

from hjemmefra.api.app import create_app
from hjemmefra.config import Settings

HH = {"X-Api-Key": "demo-key"}
ADMIN = {"X-Admin-Key": "adm"}


@pytest.fixture(scope="module")
def client():
    app = create_app(Settings(database_url="sqlite:///:memory:", admin_api_key="adm", seed_demo=True))
    with TestClient(app) as c:
        yield c


def test_health_and_openapi(client):
    assert client.get("/health").json()["status"] == "ok"
    paths = client.get("/openapi.json").json()["paths"]
    for p in ("/households", "/stores", "/offers", "/products", "/recipes", "/households/{household_id}/pantry",
              "/households/{household_id}/plans", "/optimization/modes", "/households/{household_id}/feedback", "/admin/data-quality"):
        assert p in paths


def test_household_isolation(client):
    other = client.post("/households", json={"name": "Other", "members": [{"role": "adult"}], "location": {"postal_code": "8000"}}).json()
    key = {"X-Api-Key": other["api_key"]}
    assert client.get("/households/hh_demo", headers=key).status_code == 403
    assert client.get("/households/hh_demo/pantry", headers=key).status_code == 403
    assert client.get("/households/hh_demo/plans", headers=key).status_code == 403
    assert client.get(f"/households/{other['household_id']}", headers=key).status_code == 200
    assert client.get("/households/hh_demo", headers={"X-Api-Key": "nope"}).status_code == 401
    assert client.get("/households/hh_demo").status_code == 422  # header required


def test_pantry_versioning_conflict(client):
    v = client.get("/households/hh_demo/pantry", headers=HH).json()["version"]
    r = client.post("/households/hh_demo/pantry/lots", headers=HH, json={"canonical_product_id": "EGGS", "quantity": "6", "unit": "stk", "expected_version": v})
    assert r.status_code == 201 and r.json()["version"] == v + 1
    r = client.post("/households/hh_demo/pantry/lots", headers=HH, json={"canonical_product_id": "EGGS", "quantity": "6", "unit": "stk", "expected_version": v})
    assert r.status_code == 409


def test_plan_create_get_shopping_list_and_idempotency(client):
    body = {"start_date": "2026-10-05", "days": 3, "optimization_modes": ["CHEAPEST", "ONE_STORE"], "time_limit_seconds": 5,
            "idempotency_key": "test-1", "max_stores": 3, "max_distance_km": 15}
    r = client.post("/households/hh_demo/plans", headers=HH, json=body)
    assert r.status_code == 201
    plan = r.json()
    assert plan["optimizer_version"].startswith("cpsat-") and len(plan["scenarios"]) == 2
    assert client.post("/households/hh_demo/plans", headers=HH, json=body).json()["plan_id"] == plan["plan_id"]
    pid = plan["plan_id"]
    assert client.get(f"/households/hh_demo/plans/{pid}", headers=HH).json()["plan_id"] == pid
    sl = client.get(f"/households/hh_demo/plans/{pid}/shopping-list", headers=HH, params={"scenario": "ONE_STORE"}).json()
    assert len(sl["stores"]) == 1 and sl["checkout_total_minor"] == sum(s["checkout_minor"] for s in sl["stores"])
    # pantry change after plan does not alter the stored plan
    client.post("/households/hh_demo/pantry/lots", headers=HH, json={"canonical_product_id": "RICE", "quantity": "5000", "unit": "g"})
    assert client.get(f"/households/hh_demo/plans/{pid}", headers=HH).json()["scenarios"][0]["checkout_total_minor"] == plan["scenarios"][0]["checkout_total_minor"]


def test_offer_provenance(client):
    offers = client.get("/offers", params={"valid_on": "2026-10-06", "retailer": "rema"}).json()
    prov = client.get(f"/offers/{offers[0]['offer_id']}/provenance").json()
    assert prov["source_id"] == "demo_rema" and "raw" in prov and prov["raw"]["payload"]["title"] == offers[0]["raw_title"]


def test_feedback_adjusts_rating_only_going_forward(client):
    r = client.post("/households/hh_demo/feedback", headers=HH, json={"recipe_id": "linsesuppe", "kind": "disliked"})
    assert r.status_code == 201 and r.json()["recipe_rating"] == 1
    assert client.get("/households/hh_demo/preferences", headers=HH).json()["recipe_ratings"]["linsesuppe"] == 1


def test_admin_endpoints(client):
    assert client.get("/admin/data-quality", headers={"X-Admin-Key": "bad"}).status_code == 403
    dq = client.get("/admin/data-quality", headers=ADMIN).json()
    assert dq["open_total"] >= 1
    q = client.get("/admin/data-quality/review-queue", headers=ADMIN, params={"kind": "OFFER_REQUIRES_REVIEW"}).json()
    assert q and q[0]["payload"]["title"].startswith("Laksefilet")
    imp = client.post("/admin/offers/import", headers=ADMIN, json={"source_id": "manual_x", "retailer": "rema", "records": [
        {"external_id": "m1", "title": "Kyllingebrystfilet 700 g", "valid_from": "2026-10-05", "valid_to": "2026-10-11",
         "package_quantity": "700", "package_unit": "g", "normal_price": "65.00", "offer_price": "45.00"}]}).json()
    assert imp["new_offers"] == 1
    imp2 = client.post("/admin/offers/import", headers=ADMIN, json={"source_id": "manual_x", "retailer": "rema", "records": [
        {"external_id": "m1", "title": "Kyllingebrystfilet 700 g", "valid_from": "2026-10-05", "valid_to": "2026-10-11",
         "package_quantity": "700", "package_unit": "g", "normal_price": "65.00", "offer_price": "45.00"}]}).json()
    assert imp2["new_offers"] == 0 and imp2["duplicates"] == 1
    assert "counters" in client.get("/admin/metrics", headers=ADMIN).json()
