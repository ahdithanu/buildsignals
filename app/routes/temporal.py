"""Authenticated, bounded access to recorded observations and their evidence lineage."""
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.activity_baseline import ActivityBaselineRequest, ActivityBaselineResponse
from app.schemas.temporal import EventResponse, ObservationResponse, UtcCutoff
from app.services.activity_baseline import activity_baseline
from app.services.temporal_service import events_as_of, numeric_change, observations_as_of
from app.utils.auth_deps import get_current_user

router = APIRouter(prefix="/temporal", tags=["temporal"], dependencies=[Depends(get_current_user)])


@router.post("/activity-baseline", response_model=ActivityBaselineResponse)
def get_activity_baseline(payload: ActivityBaselineRequest, db: Session = Depends(get_db)):
    """Read-only diagnostics for a pinned cohort; does not qualify market coverage."""
    try:
        return activity_baseline(db, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class NumericChangeResponse(BaseModel):
    series_key: str
    as_of: datetime
    methodology_version: str
    status: str
    current_observation_id: str | None
    previous_observation_id: str | None
    current_value: float | None
    previous_value: float | None
    absolute_change: float | None
    percent_change: float | None
    direction: str | None


@router.get("/observations", response_model=list[ObservationResponse])
def list_observations(
    as_of: UtcCutoff | None = None,
    entity_id: Annotated[str | None, Query(max_length=36)] = None,
    observation_id: Annotated[str | None, Query(max_length=36)] = None,
    attribute: Annotated[str | None, Query(max_length=100)] = None,
    series_key: Annotated[str | None, Query(pattern=r"^[a-f0-9]{64}$")] = None,
    limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0, le=10000),
    db: Session = Depends(get_db),
):
    return observations_as_of(
        db, as_of=as_of or datetime.now(timezone.utc), entity_id=entity_id,
        attribute=attribute, series_key=series_key, limit=limit, offset=offset,
        observation_id=observation_id,
    )


@router.get("/events", response_model=list[EventResponse])
def list_events(
    as_of: UtcCutoff | None = None,
    entity_id: Annotated[str | None, Query(max_length=36)] = None,
    event_type: Annotated[str | None, Query(max_length=100)] = None,
    limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0, le=10000),
    db: Session = Depends(get_db),
):
    return events_as_of(
        db, as_of=as_of or datetime.now(timezone.utc), entity_id=entity_id,
        event_type=event_type, limit=limit, offset=offset,
    )


@router.get("/changes", response_model=NumericChangeResponse)
def get_change(
    series_key: Annotated[str, Query(pattern=r"^[a-f0-9]{64}$")],
    as_of: UtcCutoff | None = None, db: Session = Depends(get_db),
):
    return numeric_change(db, series_key=series_key, as_of=as_of or datetime.now(timezone.utc))
