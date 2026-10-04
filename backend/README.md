# Hjemmefra backend

Deterministic meal-plan + grocery optimization engine for Danish households.
Prices, totals, unit conversions, offer validity, budgets, pantry and
optimization results are computed by code and are testable; no LLM is
authoritative for numbers (see `docs/adr/0004-data-trust.md`).

## Quick start
```bash
cd backend
pip install -e ".[dev]"
pytest -q                                   # full suite incl. golden + property tests
HJEMMEFRA_SEED_DEMO=1 HJEMMEFRA_ADMIN_API_KEY=adm uvicorn hjemmefra.api.app:app --reload
# OpenAPI: http://127.0.0.1:8000/docs
```
Demo household key: `demo-key` (header `X-Api-Key`). Admin header `X-Admin-Key`.

Create a plan:
```bash
curl -s -X POST localhost:8000/households/hh_demo/plans -H 'X-Api-Key: demo-key' \
  -H 'content-type: application/json' \
  -d '{"start_date":"2026-10-05","days":7,"budget_dkk":"600","max_stores":3,"max_distance_km":15,
       "optimization_modes":["CHEAPEST","BALANCED","ONE_STORE"]}'
```
Migrations: `HJEMMEFRA_DATABASE_URL=postgresql://... alembic upgrade head`.

## Demo result (golden, reproduced by `tests/optimizer/test_golden.py`)
| Scenario | Checkout | Stores | Travel est. |
|---|---|---|---|
| CHEAPEST | 203,00 kr | 3 | 26,40 kr |
| BALANCED | 240,00 kr | 2 | 5,65 kr |
| ONE_STORE | 269,00 kr | 1 | 2,15 kr |

Explanation produced from engine data (BALANCED): "240,00 kr ved kassen fordelt
på 2 butikker. Den absolut billigste plan kostede 203,00 kr med 3 butikker.
2 pantry-varer bruges. 3 retter laves i dobbelt portion og spises som rest.
100 % af checkout-prisen bygger på verificerede aktuelle priser."

## API surface
`/households`, `/households/{id}/preferences`, `/stores`, `/offers` (+ `/provenance`),
`/products`, `/recipes`, `/households/{id}/pantry`, `/households/{id}/plans`
(+ `/shopping-list`), `/optimization/modes`, `/households/{id}/feedback`,
`/admin/data-quality`, `/admin/data-quality/review-queue`, `/admin/offers/import`,
`/admin/metrics`, `/health`.

## Layout
`hjemmefra/` domain packages (see `docs/ARCHITECTURE.md`), `alembic/` migrations,
`fixtures/demo_offers.json` regression fixture, `tests/{unit,ingestion,optimizer,property,api,db}`.

## Live data sources
Adapters exist for two official APIs and a recipe importer; all are compliance-classified (ADR-0005)
and degrade gracefully (missing key or network error becomes a coverage warning, never a crash).

| Source | What | Env var | Scope mapping |
|---|---|---|---|
| Salling Group API (`/v1/food-waste`, `/v1/stores`) | Netto, Bilka, føtex clearance offers with stock; store catalog | `HJEMMEFRA_SALLING_API_TOKEN` | STORE |
| Tjek / eTilbudsavis API (`/v2/offers`) | Weekly leaflet offers for Lidl, REMA 1000, Netto, Bilka, føtex, ... | `HJEMMEFRA_TJEK_API_KEY` | REGIONAL (`tjek:<postal>`) |
| schema.org/Recipe JSON-LD importer | Recipes from pages you point at (no crawling) | none | `review_required` until ingredients resolve |

Set `HJEMMEFRA_SOURCE_POSTAL_CODE=4200` and call `POST /admin/ingestion/run`, `POST /admin/stores/import-salling`,
`POST /admin/recipes/import {"urls": [...]}`. Keys are obtained from developer.sallinggroup.com and tjek.com/developers.
Regular leaflet offers for Lidl/REMA are only available through Tjek; retailer websites are deliberately not scraped.
The cloud environment used for development blocks outbound traffic to these hosts, so the adapters are verified
against recorded fixtures in `fixtures/live/` (see `tests/ingestion/test_live_adapters.py`).

## Known limitations
- Live adapters are fixture-tested but not yet run against the real APIs (needs network + keys).
  Tjek offers are mapped to a postal-code region, not to individual stores.
- Distance is straight-line × 1.3, labelled as such; no routing provider.
- Leftovers are modelled as "cook double, eat next day"; partial-ingredient
  leftovers (e.g. 250 g cooked chicken reused in another dish) are tracked by
  the ledger but not yet chosen by the optimizer.
- One meal slot per day (dinner); breakfast/lunch slots need a slot dimension.
- Shopping trips: offers must be valid on at least one shopping date; purchases
  are not yet assigned to a specific trip when several are given.
- Nutrition is carried as data with source only; no nutrition constraints.
- Metrics are in-process; wire an exporter for production. Jobs run in-process.
- API-key auth is minimal; put behind a gateway / OAuth for production.

## Next highest-value steps
1. First real data source (official API or licensed feed) behind the adapter + freshness job.
2. Trip-level purchase assignment and multi-slot days.
3. Ingredient-level leftover reuse in the optimizer (reserved quantities feed later recipes).
4. Routing provider for real driving distances; postal centroid dataset for all of DK.
5. Review-queue UI/LLM-assisted suggestions for unmatched products (suggestions only).
6. Historical price observations fed from each ingestion run → reference prices by HISTORICAL_MEDIAN.
