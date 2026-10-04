from __future__ import annotations

from typing import Generator

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from hjemmefra.domain.household import Household
from hjemmefra.persistence.repositories import HouseholdRepo


def get_session(request: Request) -> Generator[Session, None, None]:
    factory = request.app.state.session_factory
    s = factory()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def current_household(x_api_key: str = Header(..., alias="X-Api-Key"), s: Session = Depends(get_session)) -> Household:
    hh = HouseholdRepo(s).by_api_key(x_api_key)
    if hh is None:
        raise HTTPException(status_code=401, detail="invalid API key")
    return hh


def require_household(household_id: str, hh: Household = Depends(current_household)) -> Household:
    """Access control: a key may only touch its own household."""
    if hh.household_id != household_id:
        raise HTTPException(status_code=403, detail="forbidden")
    return hh


def require_admin(request: Request, x_admin_key: str = Header(..., alias="X-Admin-Key")) -> None:
    expected = request.app.state.admin_api_key
    if not expected or x_admin_key != expected:
        raise HTTPException(status_code=403, detail="admin access required")
