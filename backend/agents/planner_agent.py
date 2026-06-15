"""Planner agent: turns a TripRequest into an Itinerary, and revises it."""
from __future__ import annotations

import json

from backend.models.schemas import Itinerary, TripRequest
from backend.services.foundry_service import LLMClient
from backend.services.logging_service import get_logger

logger = get_logger(__name__)


_SYSTEM_PROMPT = """You are a travel-planning agent. Produce a day-by-day itinerary.

Hard rules:
- Respond with a single JSON object only. No prose, no markdown fences.
- Schema:
  {
    "destination": "<str>",
    "summary": "<2-3 sentence overview>",
    "days": [
      {
        "day_number": <int starting at 1>,
        "date": "YYYY-MM-DD",
        "items": [
          {
            "title": "<str>",
            "description": "<str>",
            "category": "lodging" | "food" | "activity" | "transport" | "other",
            "estimated_cost_usd": <number>
          }
        ]
      }
    ],
    "total_estimated_cost_usd": <number>,
    "currency": "USD"
  }
- Costs are PER TRIP (not per person) and must sum across all items to
  total_estimated_cost_usd. Be realistic with prices.
- Cover lodging, food, transport, and activities for each day.
- Honor travel_style, interests, and party_size from the request.
"""


def _format_request(req: TripRequest) -> str:
    return json.dumps(
        {
            "destination": req.destination,
            "start_date": req.start_date.isoformat(),
            "end_date": req.end_date.isoformat(),
            "days": req.days,
            "party_size": req.party_size,
            "budget_usd": req.budget_usd,
            "travel_style": req.travel_style.value,
            "interests": req.interests,
            "notes": req.notes,
        },
        indent=2,
    )


class PlannerAgent:
    def __init__(self, llm: LLMClient):
        self._llm = llm

    async def generate(self, request: TripRequest) -> Itinerary:
        user = (
            "Create an itinerary for this trip request:\n"
            f"{_format_request(request)}\n\n"
            f"Target total cost: ≤ ${request.budget_usd:.2f} USD."
        )
        logger.info("planner.generate.start", destination=request.destination)
        data = await self._llm.chat_json(
            system_prompt=_SYSTEM_PROMPT, user_prompt=user, temperature=0.5
        )
        itinerary = Itinerary.model_validate(data)
        logger.info(
            "planner.generate.done",
            total_cost=itinerary.total_estimated_cost_usd,
            days=len(itinerary.days),
        )
        return itinerary

    async def revise(
        self,
        request: TripRequest,
        previous: Itinerary,
        feedback: list[str],
    ) -> Itinerary:
        user = (
            "Revise the itinerary below to fit the budget. Apply the budget "
            "agent's feedback exactly. Keep the same destination and date range.\n\n"
            f"Trip request:\n{_format_request(request)}\n\n"
            f"Previous itinerary (over budget):\n{previous.model_dump_json(indent=2)}\n\n"
            f"Budget feedback:\n- " + "\n- ".join(feedback)
        )
        logger.info("planner.revise.start", feedback_count=len(feedback))
        data = await self._llm.chat_json(
            system_prompt=_SYSTEM_PROMPT, user_prompt=user, temperature=0.4
        )
        itinerary = Itinerary.model_validate(data)
        logger.info(
            "planner.revise.done", total_cost=itinerary.total_estimated_cost_usd
        )
        return itinerary
