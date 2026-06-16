"""REST routes for the planning service."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.coordinator import Coordinator
from backend.db.database import TripRun, get_session
from backend.models.schemas import PlanRecord, PlanResponse, PlanStatus, TripRequest
from backend.services.logging_service import get_logger

router = APIRouter(prefix="/api", tags=["planner"])
logger = get_logger(__name__)


def _coordinator(request: Request) -> Coordinator:
    """Pull the singleton coordinator off app.state (set during lifespan)."""
    coordinator: Coordinator | None = getattr(request.app.state, "coordinator", None)
    if coordinator is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Coordinator not initialized",
        )
    return coordinator


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post(
    "/trips/plan",
    response_model=PlanResponse,
    status_code=status.HTTP_200_OK,
)
async def plan_trip(
    trip_request: TripRequest,
    coordinator: Coordinator = Depends(_coordinator),
    session: AsyncSession = Depends(get_session),
) -> PlanResponse:
    return await coordinator.plan(trip_request, session)


@router.get("/trips/{trip_id}", response_model=PlanRecord)
async def get_trip(
    trip_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> PlanRecord:
    row = (
        await session.execute(select(TripRun).where(TripRun.id == trip_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Trip not found")

    return PlanRecord(
        trip_id=row.id,
        status=PlanStatus(row.status),
        iterations=row.iterations,
        request=row.request_json,  
        itinerary=row.itinerary_json,  
        validation=row.validation_json,  
        created_at=row.created_at.isoformat(),
    )
