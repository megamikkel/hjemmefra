from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from hjemmefra.api.deps import get_session, require_household
from hjemmefra.api.schemas import PantryLotCreate
from hjemmefra.core.errors import ConflictError, NotFound
from hjemmefra.core.ids import new_id
from hjemmefra.domain.household import Household
from hjemmefra.domain.pantry import InventoryLot, PantrySnapshot
from hjemmefra.persistence.repositories import PantryRepo

router = APIRouter(prefix="/households/{household_id}/pantry", tags=["pantry"])


@router.get("", response_model=PantrySnapshot)
def get_pantry(household_id: str, hh: Household = Depends(require_household), s: Session = Depends(get_session)):
    repo = PantryRepo(s)
    return PantrySnapshot(household_id=household_id, version=repo.version(household_id), lots=repo.lots(household_id))


@router.post("/lots", response_model=PantrySnapshot, status_code=201)
def add_lot(household_id: str, body: PantryLotCreate, hh: Household = Depends(require_household), s: Session = Depends(get_session)):
    repo = PantryRepo(s)
    lot = InventoryLot(lot_id=new_id("lot"), household_id=household_id, **body.model_dump(exclude={"expected_version"}))
    try:
        v = repo.add(lot, body.expected_version)
    except ConflictError as exc:
        raise HTTPException(409, str(exc))
    return PantrySnapshot(household_id=household_id, version=v, lots=repo.lots(household_id))


@router.delete("/lots/{lot_id}", response_model=PantrySnapshot)
def delete_lot(household_id: str, lot_id: str, hh: Household = Depends(require_household), s: Session = Depends(get_session)):
    repo = PantryRepo(s)
    try:
        v = repo.delete(household_id, lot_id)
    except NotFound:
        raise HTTPException(404, "lot not found")
    return PantrySnapshot(household_id=household_id, version=v, lots=repo.lots(household_id))
