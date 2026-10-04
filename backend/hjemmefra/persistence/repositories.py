"""Repositories: translate between pydantic domain models and ORM rows.
All queries are parameterised through SQLAlchemy (no string SQL)."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Iterable, List, Optional, Sequence

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from hjemmefra.core.errors import ConflictError, NotFound
from hjemmefra.domain.household import Household
from hjemmefra.domain.offer import NormalizedOffer, PriceObservation, RawOfferRecord
from hjemmefra.domain.pantry import InventoryLot
from hjemmefra.domain.plan import PlanResult
from hjemmefra.domain.product import CanonicalProduct
from hjemmefra.domain.recipe import Recipe
from hjemmefra.domain.store import Chain, Store
from hjemmefra.persistence import models as M


def _doc(model) -> dict:
    return json.loads(model.model_dump_json())


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


class HouseholdRepo:
    def __init__(self, s: Session):
        self.s = s

    def create(self, hh: Household, api_key: str) -> Household:
        self.s.add(M.HouseholdRow(household_id=hh.household_id, name=hh.name, api_key_hash=hash_api_key(api_key),
                                  postal_code=hh.location.postal_code, document=_doc(hh), version=hh.version))
        self.s.add(M.PantryVersionRow(household_id=hh.household_id, version=1))
        return hh

    def get(self, household_id: str) -> Household:
        row = self.s.get(M.HouseholdRow, household_id)
        if row is None:
            raise NotFound(f"household {household_id}")
        return Household.model_validate(row.document)

    def by_api_key(self, api_key: str) -> Optional[Household]:
        row = self.s.scalar(select(M.HouseholdRow).where(M.HouseholdRow.api_key_hash == hash_api_key(api_key)))
        return Household.model_validate(row.document) if row else None

    def save(self, hh: Household, expected_version: Optional[int] = None) -> Household:
        row = self.s.get(M.HouseholdRow, hh.household_id)
        if row is None:
            raise NotFound(hh.household_id)
        if expected_version is not None and row.version != expected_version:
            raise ConflictError(f"household version {row.version} != expected {expected_version}")
        hh.version = row.version + 1
        row.version = hh.version
        row.document = _doc(hh)
        row.postal_code = hh.location.postal_code
        row.updated_at = datetime.utcnow()
        return hh


class StoreRepo:
    def __init__(self, s: Session):
        self.s = s

    def upsert_chain(self, c: Chain) -> None:
        self.s.merge(M.ChainRow(chain_id=c.chain_id, document=_doc(c)))

    def upsert(self, st: Store) -> None:
        self.s.merge(M.StoreRow(store_id=st.store_id, chain_id=st.chain_id, postal_code=st.postal_code, region=st.region, document=_doc(st)))

    def all(self) -> List[Store]:
        return [Store.model_validate(r.document) for r in self.s.scalars(select(M.StoreRow).order_by(M.StoreRow.store_id))]

    def chains(self) -> List[Chain]:
        return [Chain.model_validate(r.document) for r in self.s.scalars(select(M.ChainRow))]

    def get(self, store_id: str) -> Store:
        row = self.s.get(M.StoreRow, store_id)
        if row is None:
            raise NotFound(store_id)
        return Store.model_validate(row.document)


class ProductRepo:
    def __init__(self, s: Session):
        self.s = s

    def upsert(self, p: CanonicalProduct) -> None:
        self.s.merge(M.ProductRow(canonical_id=p.canonical_id, category=p.category, substitution_group=p.substitution_group,
                                  version=p.version, document=_doc(p)))
        for a in [p.name, *p.aliases]:
            self.s.merge(M.ProductAliasRow(alias=a.lower(), canonical_id=p.canonical_id))

    def all(self) -> List[CanonicalProduct]:
        return [CanonicalProduct.model_validate(r.document) for r in self.s.scalars(select(M.ProductRow).order_by(M.ProductRow.canonical_id))]

    def get(self, cid: str) -> CanonicalProduct:
        row = self.s.get(M.ProductRow, cid)
        if row is None:
            raise NotFound(cid)
        return CanonicalProduct.model_validate(row.document)


class OfferRepo:
    def __init__(self, s: Session):
        self.s = s

    def store_raw(self, raws: Iterable[RawOfferRecord]) -> None:
        for r in raws:
            self.s.merge(M.RawOfferRow(raw_id=r.raw_id, source_id=r.source_id, captured_at=r.captured_at.replace(tzinfo=None), document=_doc(r)))

    def existing_by_fingerprint(self) -> dict[str, NormalizedOffer]:
        return {r.fingerprint: NormalizedOffer.model_validate(r.document) for r in self.s.scalars(select(M.OfferRow))}

    def upsert(self, offers: Iterable[NormalizedOffer]) -> int:
        n = 0
        for o in offers:
            row = self.s.scalar(select(M.OfferRow).where(M.OfferRow.fingerprint == o.fingerprint))
            if row is None:
                row = M.OfferRow(offer_id=o.offer_id, fingerprint=o.fingerprint, raw_id=o.raw_id)
                self.s.add(row)
                n += 1
            else:
                o.version = row.version + 1
            row.source_id, row.retailer, row.scope, row.store_id, row.region = o.source_id, o.retailer, o.scope.value, o.store_id, o.region
            row.canonical_product_id, row.valid_from, row.valid_to = o.canonical_product_id, o.valid_from, o.valid_to
            row.validation_status, row.price_confidence, row.version = o.validation_status.value, o.price_confidence.value, o.version
            row.last_verified_at = o.last_verified_at.replace(tzinfo=None)
            row.document = _doc(o)
        return n

    def valid_on(self, day: date, retailers: Optional[Sequence[str]] = None) -> List[NormalizedOffer]:
        q = select(M.OfferRow).where(M.OfferRow.valid_from <= day, M.OfferRow.valid_to >= day)
        if retailers:
            q = q.where(M.OfferRow.retailer.in_(list(retailers)))
        return [NormalizedOffer.model_validate(r.document) for r in self.s.scalars(q.order_by(M.OfferRow.offer_id))]

    def all(self) -> List[NormalizedOffer]:
        return [NormalizedOffer.model_validate(r.document) for r in self.s.scalars(select(M.OfferRow).order_by(M.OfferRow.offer_id))]

    def get(self, offer_id: str) -> NormalizedOffer:
        row = self.s.get(M.OfferRow, offer_id)
        if row is None:
            raise NotFound(offer_id)
        return NormalizedOffer.model_validate(row.document)

    def raw(self, raw_id: str) -> RawOfferRecord:
        row = self.s.get(M.RawOfferRow, raw_id)
        if row is None:
            raise NotFound(raw_id)
        return RawOfferRecord.model_validate(row.document)

    def add_observations(self, obs: Iterable[PriceObservation]) -> None:
        for o in obs:
            self.s.add(M.PriceObservationRow(canonical_product_id=o.canonical_product_id, retailer=o.retailer, observed_on=o.observed_on,
                                             unit_price_minor_per_base=o.unit_price_minor_per_base, is_offer=o.is_offer,
                                             source_id=o.source_id, confidence=o.confidence.value))

    def observations(self, canonical_id: Optional[str] = None) -> List[PriceObservation]:
        q = select(M.PriceObservationRow)
        if canonical_id:
            q = q.where(M.PriceObservationRow.canonical_product_id == canonical_id)
        return [PriceObservation(canonical_product_id=r.canonical_product_id, retailer=r.retailer, observed_on=r.observed_on,
                                 unit_price_minor_per_base=r.unit_price_minor_per_base, is_offer=r.is_offer, source_id=r.source_id,
                                 confidence=r.confidence) for r in self.s.scalars(q.order_by(M.PriceObservationRow.observed_on))]


class RecipeRepo:
    def __init__(self, s: Session):
        self.s = s

    def upsert(self, r: Recipe) -> None:
        self.s.merge(M.RecipeRow(recipe_id=r.recipe_id, version=r.version, main_protein=r.main_protein, document=_doc(r)))

    def all(self) -> List[Recipe]:
        return [Recipe.model_validate(r.document) for r in self.s.scalars(select(M.RecipeRow).order_by(M.RecipeRow.recipe_id))]

    def get(self, rid: str) -> Recipe:
        row = self.s.get(M.RecipeRow, rid)
        if row is None:
            raise NotFound(rid)
        return Recipe.model_validate(row.document)


class PantryRepo:
    def __init__(self, s: Session):
        self.s = s

    def version(self, household_id: str) -> int:
        row = self.s.get(M.PantryVersionRow, household_id)
        return row.version if row else 0

    def _bump(self, household_id: str, expected: Optional[int]) -> int:
        row = self.s.get(M.PantryVersionRow, household_id)
        if row is None:
            row = M.PantryVersionRow(household_id=household_id, version=0)
            self.s.add(row)
        if expected is not None and row.version != expected:
            raise ConflictError(f"pantry version {row.version} != expected {expected}")
        row.version += 1
        return row.version

    def lots(self, household_id: str) -> List[InventoryLot]:
        q = select(M.PantryLotRow).where(M.PantryLotRow.household_id == household_id).order_by(M.PantryLotRow.lot_id)
        return [InventoryLot.model_validate(r.document) for r in self.s.scalars(q)]

    def add(self, lot: InventoryLot, expected_version: Optional[int] = None) -> int:
        self.s.merge(M.PantryLotRow(lot_id=lot.lot_id, household_id=lot.household_id, canonical_product_id=lot.canonical_product_id,
                                    expiry_date=lot.expiry_date, document=_doc(lot)))
        return self._bump(lot.household_id, expected_version)

    def delete(self, household_id: str, lot_id: str, expected_version: Optional[int] = None) -> int:
        row = self.s.get(M.PantryLotRow, lot_id)
        if row is None or row.household_id != household_id:
            raise NotFound(lot_id)
        self.s.delete(row)
        return self._bump(household_id, expected_version)


class PlanRepo:
    def __init__(self, s: Session):
        self.s = s

    def save(self, plan: PlanResult, idempotency_key: Optional[str] = None) -> None:
        self.s.add(M.PlanRow(plan_id=plan.plan_id, household_id=plan.household_id, created_at=plan.created_at.replace(tzinfo=None),
                             optimizer_version=plan.optimizer_version, idempotency_key=idempotency_key, document=_doc(plan)))

    def by_idempotency(self, household_id: str, key: str) -> Optional[PlanResult]:
        row = self.s.scalar(select(M.PlanRow).where(M.PlanRow.household_id == household_id, M.PlanRow.idempotency_key == key))
        return PlanResult.model_validate(row.document) if row else None

    def get(self, plan_id: str) -> PlanResult:
        row = self.s.get(M.PlanRow, plan_id)
        if row is None:
            raise NotFound(plan_id)
        return PlanResult.model_validate(row.document)

    def list_for(self, household_id: str) -> List[PlanResult]:
        q = select(M.PlanRow).where(M.PlanRow.household_id == household_id).order_by(M.PlanRow.created_at.desc())
        return [PlanResult.model_validate(r.document) for r in self.s.scalars(q)]


class FeedbackRepo:
    def __init__(self, s: Session):
        self.s = s

    def add(self, household_id: str, recipe_id: str, kind: str, plan_id: Optional[str], comment: Optional[str]) -> int:
        row = M.FeedbackRow(household_id=household_id, recipe_id=recipe_id, kind=kind, plan_id=plan_id, comment=comment)
        self.s.add(row)
        self.s.flush()
        return row.id

    def for_household(self, household_id: str) -> List[M.FeedbackRow]:
        return list(self.s.scalars(select(M.FeedbackRow).where(M.FeedbackRow.household_id == household_id)))


class ReviewRepo:
    def __init__(self, s: Session):
        self.s = s

    def add(self, kind: str, payload: dict) -> None:
        self.s.add(M.ReviewItemRow(kind=kind, payload=payload))

    def open(self, kind: Optional[str] = None) -> List[M.ReviewItemRow]:
        q = select(M.ReviewItemRow).where(M.ReviewItemRow.status == "OPEN")
        if kind:
            q = q.where(M.ReviewItemRow.kind == kind)
        return list(self.s.scalars(q.order_by(M.ReviewItemRow.id)))

    def resolve(self, item_id: int, resolution: dict) -> None:
        row = self.s.get(M.ReviewItemRow, item_id)
        if row is None:
            raise NotFound(str(item_id))
        row.status = "RESOLVED"
        row.resolution = resolution


class JobRepo:
    def __init__(self, s: Session):
        self.s = s

    def record(self, job_name: str, status: str, attempts: int, started_at: datetime, finished_at: Optional[datetime],
               error: Optional[str], summary: Optional[dict]) -> None:
        self.s.add(M.JobRunRow(job_name=job_name, status=status, attempts=attempts, started_at=started_at, finished_at=finished_at,
                               error=error, summary=summary))
