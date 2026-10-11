# Hjemmefra backend architecture

```
offers (adapters) → normalize → resolve product → validate → dedupe → OfferRepo
recipes + household + pantry ──┐
                               ├→ match ingredients ↔ purchase options (per store)
stores (locality filter) ──────┘
          → candidate recipes (hard filters, coverage, ranking, Top-K)
          → CP-SAT model (meals, packages, stores, pantry, leftovers, budget)
          → Scenario per mode (purchases, store breakdown, meals, waste, confidence)
          → explanations (structured → text) → PlanResult + DataSnapshot → PlanRepo
```

## Package boundaries (`hjemmefra/`)
| Package | Responsibility |
|---|---|
| `core` | Money (øre), units/dimensions, confidence enums, logging, metrics, ids |
| `domain` | Pydantic models: household, store, product, offer, recipe, pantry, leftover, plan |
| `ingestion` | `SourceAdapter` interface, adapters (manual JSON, failing), normalizer (OCR-aware), validation pipeline, dedup, orchestration |
| `catalog` | Canonical product resolver with alias/negative-alias matching and match confidence |
| `matching` | Recipe ingredient → purchasable options (attributes, allergens, diet, scope, validity, membership, unit compatibility) with explanations |
| `pricing` | Package cost under multi-buy/min/max/member/coupon/deposit rules, cost tables, reference price methods, consumed value |
| `location` | Postal-code based store filtering, approximate distance and travel cost |
| `pantry` | Usability rules (CONFIRMED/ESTIMATED only, expiry, FEFO allocation) |
| `leftovers` | Ledger preventing double spending; estimated expiry |
| `planning` | Candidate generation/pruning, explainable preference scoring, orchestration (`generate_plan`) |
| `optimization` | Mode weights, CP-SAT model, result extraction, scenarios, trade-off explanations |
| `persistence` | SQLAlchemy models, repositories, versioning/optimistic concurrency |
| `api` | FastAPI routers, API-key auth per household, admin key |
| `jobs` | Retryable job runner, ingestion job |
| `admin` | Data-quality summary / review queue kinds |
| `demo` | Deterministic dataset and seed |

## Objective (BALANCED defaults, `ObjectiveWeights`)
objective = checkout_cost + travel_cost + 15 kr × (stores − 1) + waste_penalty
            − 3 kr × preference_points + 0 × minutes + 20 kr × consecutive-day repeats
            + 5 kr × low-confidence packages + 3 × soft budget overrun

Waste penalty (hundredths of øre per unused base unit): perishable 150 (15 kr/kg),
chilled 60, ambient/frozen 10, count items 300. Travel: 2,50 kr/km round trip
on approximate distance, value of time 0 by default. All weights are
configurable per request (`CUSTOM`) and exposed at `/optimization/modes`.

Mode overrides: CHEAPEST zeroes travel/store/waste/preference weights and
requires HIGH price confidence; ONE_STORE sets max_stores=1; LOW_WASTE ×5 waste;
FAST 0,50 kr/min; FAMILY 10 kr/preference point; BUDGET makes the budget hard.

## Hard vs soft constraints
Hard (model constraints or pre-filters): allergens, excluded ingredients, diet,
max prep time (when set), offer validity on shopping date, store scope,
membership/coupon eligibility, max stores, max distance, one meal per day,
recipe repeat cap, package coverage, pantry non-negativity, hard budget,
minimum price confidence. Soft (objective terms): preferences, variety, waste,
time, store count beyond the first, travel, soft budget.

Infeasibility → `status: NO_FEASIBLE_PLAN` with reason; for hard budgets the
minimum required budget is computed and a clearly labelled `NEXT_BEST_PLAN`
(relaxed_constraints=["BUDGET"]) is appended.

## Data trust
See ADR-0004. Checkout totals are sums of purchase lines; each line names the
store, offer, validity window, packages, consumed/remainder quantity, product
cost, deposit, reference method and confidences. `/offers/{id}/provenance`
answers "where did this price come from?".

## Versioning & reproducibility
Offers, recipes, products, households and pantry carry versions. A plan stores
`optimizer_version` and a `DataSnapshot` (offer ids + versions, recipe/product
versions, pantry/household versions, weights). Plans are immutable; feedback only
affects future rankings. Plan creation accepts an idempotency key.

## Observability
structlog JSON logs (no PII), in-process `MetricsRegistry` exposed at
`/admin/metrics`: ingestion/validation counts by status, product match
confidence, optimizer runtime by mode/status, plan generation outcomes,
candidate counts, source freshness, job runs.

## Database
16 tables (Alembic migration `alembic/versions`). Hot paths indexed: offers by
retailer + validity window, store_id, canonical product, validation status;
price observations by product/time and product/retailer/time; plans by
household/created_at; stores by postal code/region. JSON documents hold the full
domain objects for flexibility; promote fields to columns as queries demand.

## Known limitations / next steps
See README.
