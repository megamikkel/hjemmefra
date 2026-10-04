from __future__ import annotations

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from hjemmefra.api.deps import get_session
from hjemmefra.core.errors import NotFound
from hjemmefra.domain.offer import NormalizedOffer, RawOfferRecord
from hjemmefra.domain.product import CanonicalProduct
from hjemmefra.domain.recipe import Recipe
from hjemmefra.domain.store import Store
from hjemmefra.persistence.repositories import OfferRepo, ProductRepo, RecipeRepo, StoreRepo

router = APIRouter(tags=["catalog"])


@router.get("/stores", response_model=List[Store])
def list_stores(postal_code: Optional[str] = None, s: Session = Depends(get_session)):
    stores = StoreRepo(s).all()
    return [st for st in stores if postal_code is None or st.postal_code == postal_code]


@router.get("/offers", response_model=List[NormalizedOffer])
def list_offers(valid_on: Optional[date] = Query(default=None), retailer: Optional[str] = None, s: Session = Depends(get_session)):
    repo = OfferRepo(s)
    if valid_on:
        return repo.valid_on(valid_on, [retailer] if retailer else None)
    return [o for o in repo.all() if retailer is None or o.retailer == retailer]


@router.get("/offers/{offer_id}", response_model=NormalizedOffer)
def get_offer(offer_id: str, s: Session = Depends(get_session)):
    try:
        return OfferRepo(s).get(offer_id)
    except NotFound:
        raise HTTPException(404, "offer not found")


@router.get("/offers/{offer_id}/provenance")
def offer_provenance(offer_id: str, s: Session = Depends(get_session)):
    """Answer 'where did this price come from?'."""
    repo = OfferRepo(s)
    try:
        o = repo.get(offer_id)
        raw = repo.raw(o.raw_id)
    except NotFound:
        raise HTTPException(404, "offer not found")
    return {"offer_id": o.offer_id, "source_id": o.source_id, "source_type": o.source_type, "source_reference": o.source_reference,
            "captured_at": o.captured_at, "last_verified_at": o.last_verified_at, "price_confidence": o.price_confidence,
            "validation_status": o.validation_status, "validation_notes": o.validation_notes, "raw": raw}


@router.get("/products", response_model=List[CanonicalProduct])
def list_products(s: Session = Depends(get_session)):
    return ProductRepo(s).all()


@router.get("/recipes", response_model=List[Recipe])
def list_recipes(s: Session = Depends(get_session)):
    return RecipeRepo(s).all()


@router.get("/recipes/{recipe_id}", response_model=Recipe)
def get_recipe(recipe_id: str, s: Session = Depends(get_session)):
    try:
        return RecipeRepo(s).get(recipe_id)
    except NotFound:
        raise HTTPException(404, "recipe not found")
