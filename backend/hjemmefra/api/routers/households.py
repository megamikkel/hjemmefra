from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from hjemmefra.api.deps import get_session, require_household
from hjemmefra.api.schemas import HouseholdCreate, HouseholdCreated
from hjemmefra.core.ids import new_id
from hjemmefra.domain.household import Household, Preferences
from hjemmefra.persistence.repositories import HouseholdRepo

router = APIRouter(prefix="/households", tags=["households"])


@router.post("", response_model=HouseholdCreated, status_code=201)
def create_household(body: HouseholdCreate, s: Session = Depends(get_session)):
    hh = Household(household_id=new_id("hh"), **body.model_dump())
    key = secrets.token_urlsafe(24)
    HouseholdRepo(s).create(hh, key)
    return HouseholdCreated(household_id=hh.household_id, api_key=key)


@router.get("/{household_id}", response_model=Household)
def get_household(household_id: str, hh: Household = Depends(require_household)):
    return hh


@router.get("/{household_id}/preferences", response_model=Preferences, tags=["preferences"])
def get_preferences(household_id: str, hh: Household = Depends(require_household)):
    return hh.preferences


@router.put("/{household_id}/preferences", response_model=Household, tags=["preferences"])
def put_preferences(household_id: str, prefs: Preferences, hh: Household = Depends(require_household), s: Session = Depends(get_session)):
    hh.preferences = prefs
    return HouseholdRepo(s).save(hh)
