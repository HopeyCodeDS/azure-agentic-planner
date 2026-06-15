"""Coordinator: orchestrates the planner ↔ budget revision loop."""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.budget_agent import BudgetAgent
from backend.agents.planner_agent import PlannerAgent
from backend.core.config import get_settings
from backend.db.database import TripRun
from backend.models.schemas import (
    BudgetValidation,
    Itinerary,
    PlanResponse,
    PlanStatus,
    TripRequest,
)
from backend.services.foundry_service import LLMClient
from backend.services.logging_service import get_logger

logger = get_logger(__name__)


class Coordinator:
    def __init__(self, llm: LLMClient):
        self._planner = PlannerAgent(llm)
        self._budget = BudgetAgent(llm)
        self._max_iterations = get_settings().max_planning_iterations

    async def plan(
        self, request: TripRequest, session: AsyncSession
    ) -> PlanResponse:
        trip_id = uuid.uuid4()
        log = logger.bind(trip_id=str(trip_id), destination=request.destination)
        log.info("coordinator.start", budget=request.budget_usd, days=request.days)

        itinerary: Itinerary = await self._planner.generate(request)
        validation: BudgetValidation = await self._budget.validate(request, itinerary)
        iterations = 1

        while not validation.is_within_budget and iterations < self._max_iterations:
            log.info(
                "coordinator.revise",
                iteration=iterations,
                overage=validation.overage_usd,
            )
            itinerary = await self._planner.revise(
                request, itinerary, validation.feedback
            )
            validation = await self._budget.validate(request, itinerary)
            iterations += 1

        status = (
            PlanStatus.APPROVED
            if validation.is_within_budget
            else PlanStatus.BUDGET_EXCEEDED
        )
        log.info(
            "coordinator.done",
            status=status.value,
            iterations=iterations,
            total_cost=validation.total_cost_usd,
        )

        await self._persist(
            session, trip_id, status, iterations, request, itinerary, validation
        )

        return PlanResponse(
            trip_id=trip_id,
            status=status,
            iterations=iterations,
            itinerary=itinerary,
            validation=validation,
        )

    @staticmethod
    async def _persist(
        session: AsyncSession,
        trip_id: uuid.UUID,
        status: PlanStatus,
        iterations: int,
        request: TripRequest,
        itinerary: Itinerary,
        validation: BudgetValidation,
    ) -> None:
        row = TripRun(
            id=trip_id,
            status=status.value,
            iterations=iterations,
            request_json=request.model_dump(mode="json"),
            itinerary_json=itinerary.model_dump(mode="json"),
            validation_json=validation.model_dump(mode="json"),
        )
        session.add(row)
        await session.commit()
