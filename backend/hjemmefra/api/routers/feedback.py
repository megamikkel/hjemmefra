from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from hjemmefra.api.deps import get_session, require_household
from hjemmefra.api.schemas import FeedbackCreate
from hjemmefra.domain.household import Household
from hjemmefra.persistence.repositories import FeedbackRepo, HouseholdRepo

router = APIRouter(prefix="/households/{household_id}/feedback", tags=["feedback"])

# Feedback -> preference adjustments (explainable; historical plans are never changed).
_RATING_DELTA = {"liked": 1, "would_make_again": 1, "disliked": -2, "skip_recipe": -1, "too_difficult": -1,
                 "too_expensive": 0, "too_much_food": 0, "too_little_food": 0}


@router.post("", status_code=201)
def add_feedback(household_id: str, body: FeedbackCreate, hh: Household = Depends(require_household), s: Session = Depends(get_session)):
    fid = FeedbackRepo(s).add(household_id, body.recipe_id, body.kind, body.plan_id, body.comment)
    delta = _RATING_DELTA.get(body.kind, 0)
    if delta:
        current = hh.preferences.recipe_ratings.get(body.recipe_id, 3)
        hh.preferences.recipe_ratings[body.recipe_id] = max(1, min(5, current + delta))
        HouseholdRepo(s).save(hh)
    return {"feedback_id": fid, "recipe_rating": hh.preferences.recipe_ratings.get(body.recipe_id)}


@router.get("")
def list_feedback(household_id: str, hh: Household = Depends(require_household), s: Session = Depends(get_session)):
    return [{"id": f.id, "recipe_id": f.recipe_id, "kind": f.kind, "plan_id": f.plan_id, "created_at": f.created_at}
            for f in FeedbackRepo(s).for_household(household_id)]
