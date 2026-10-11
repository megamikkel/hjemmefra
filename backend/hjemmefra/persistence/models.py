"""SQLAlchemy ORM models. Structured documents (preferences, recipes, plan
results) are stored as JSON columns; hot query paths get real columns + indexes.
Indexes are designed for: offer validity + retailer lookups, store filtering by
postal code, price history time-series per product, plan lookup per household."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from hjemmefra.persistence.db import Base


class HouseholdRow(Base):
    __tablename__ = "households"
    household_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    api_key_hash: Mapped[str] = mapped_column(String(64), index=True)
    postal_code: Mapped[str] = mapped_column(String(10), index=True)
    document: Mapped[dict] = mapped_column(JSON)  # full Household model
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ChainRow(Base):
    __tablename__ = "chains"
    chain_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document: Mapped[dict] = mapped_column(JSON)


class StoreRow(Base):
    __tablename__ = "stores"
    store_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    chain_id: Mapped[str] = mapped_column(String(64), ForeignKey("chains.chain_id"), index=True)
    postal_code: Mapped[str] = mapped_column(String(10), index=True)
    region: Mapped[str | None] = mapped_column(String(64), index=True)
    document: Mapped[dict] = mapped_column(JSON)


class ProductRow(Base):
    __tablename__ = "canonical_products"
    canonical_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    category: Mapped[str] = mapped_column(String(64), index=True)
    substitution_group: Mapped[str | None] = mapped_column(String(64), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    document: Mapped[dict] = mapped_column(JSON)


class ProductAliasRow(Base):
    __tablename__ = "product_aliases"
    alias: Mapped[str] = mapped_column(String(200), primary_key=True)
    canonical_id: Mapped[str] = mapped_column(String(64), ForeignKey("canonical_products.canonical_id"), index=True)


class RawOfferRow(Base):
    __tablename__ = "raw_offers"
    raw_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(64), index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    document: Mapped[dict] = mapped_column(JSON)


class OfferRow(Base):
    __tablename__ = "offers"
    offer_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    raw_id: Mapped[str] = mapped_column(String(64), ForeignKey("raw_offers.raw_id"))
    source_id: Mapped[str] = mapped_column(String(64), index=True)
    retailer: Mapped[str] = mapped_column(String(64))
    scope: Mapped[str] = mapped_column(String(16))
    store_id: Mapped[str | None] = mapped_column(String(64), index=True)
    region: Mapped[str | None] = mapped_column(String(64))
    canonical_product_id: Mapped[str | None] = mapped_column(String(64), index=True)
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date] = mapped_column(Date)
    validation_status: Mapped[str] = mapped_column(String(20), index=True)
    price_confidence: Mapped[str] = mapped_column(String(20))
    version: Mapped[int] = mapped_column(Integer, default=1)
    last_verified_at: Mapped[datetime] = mapped_column(DateTime)
    document: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (Index("ix_offers_retailer_validity", "retailer", "valid_from", "valid_to"),)


class PriceObservationRow(Base):
    __tablename__ = "price_observations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    canonical_product_id: Mapped[str] = mapped_column(String(64))
    retailer: Mapped[str] = mapped_column(String(64))
    observed_on: Mapped[date] = mapped_column(Date)
    unit_price_minor_per_base: Mapped[object] = mapped_column(Numeric(14, 4))
    is_offer: Mapped[bool] = mapped_column(Boolean)
    source_id: Mapped[str] = mapped_column(String(64))
    confidence: Mapped[str] = mapped_column(String(20))
    __table_args__ = (Index("ix_price_obs_product_time", "canonical_product_id", "observed_on"),
                      Index("ix_price_obs_product_retailer_time", "canonical_product_id", "retailer", "observed_on"))


class RecipeRow(Base):
    __tablename__ = "recipes"
    recipe_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    main_protein: Mapped[str | None] = mapped_column(String(32), index=True)
    document: Mapped[dict] = mapped_column(JSON)


class PantryLotRow(Base):
    __tablename__ = "pantry_lots"
    lot_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    household_id: Mapped[str] = mapped_column(String(64), ForeignKey("households.household_id"), index=True)
    canonical_product_id: Mapped[str] = mapped_column(String(64), index=True)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    document: Mapped[dict] = mapped_column(JSON)


class PantryVersionRow(Base):
    __tablename__ = "pantry_versions"
    household_id: Mapped[str] = mapped_column(String(64), ForeignKey("households.household_id"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=1)


class PlanRow(Base):
    __tablename__ = "plans"
    plan_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    household_id: Mapped[str] = mapped_column(String(64), ForeignKey("households.household_id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    optimizer_version: Mapped[str] = mapped_column(String(32))
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    document: Mapped[dict] = mapped_column(JSON)  # immutable PlanResult incl. data snapshot
    __table_args__ = (UniqueConstraint("household_id", "idempotency_key", name="uq_plan_idem"),)


class FeedbackRow(Base):
    __tablename__ = "feedback"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    household_id: Mapped[str] = mapped_column(String(64), ForeignKey("households.household_id"), index=True)
    plan_id: Mapped[str | None] = mapped_column(String(64))
    recipe_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    comment: Mapped[str | None] = mapped_column(Text)


class ReviewItemRow(Base):
    __tablename__ = "review_queue"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(16), default="OPEN", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    payload: Mapped[dict] = mapped_column(JSON)
    resolution: Mapped[dict | None] = mapped_column(JSON)


class JobRunRow(Base):
    __tablename__ = "job_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_name: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(16))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    error: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[dict | None] = mapped_column(JSON)
