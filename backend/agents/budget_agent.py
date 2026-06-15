"""
Budget agent: validates an itinerary against the trip budget.
"""
from __future__ import annotations

from backend.models.schemas import BudgetValidation, Itinerary, TripRequest
from backend.services.foundry_service import LLMClient
from backend.services.logging_service import get_logger
from backend.services.pricing_service import baseline_per_day, estimate_baseline_total

logger = get_logger(__name__)


_SYSTEM_PROMPT = """You are a budget-review agent. Given a trip request, an over-budget
itinerary, and pricing context, produce concrete, actionable revisions.

Respond with a single JSON object only:
{
  "feedback": ["<short, specific suggestion>", ...]
}

Each suggestion must be specific and quantitative when possible (e.g. "swap
the 4-star hotel for a 3-star — saves ~$60/night"). Aim for 3-6 bullets that,
together, close the overage gap. Do not restate the overage amount.
"""


class BudgetAgent:
    def __init__(self, llm: LLMClient):
        self._llm = llm

    @staticmethod
    def _sum_items(itinerary: Itinerary) -> float:
        return round(
            sum(i.estimated_cost_usd for d in itinerary.days for i in d.items), 2
        )

    async def validate(
        self, request: TripRequest, itinerary: Itinerary
    ) -> BudgetValidation:
        total = self._sum_items(itinerary)
        overage = round(total - request.budget_usd, 2)
        within = overage <= 0

        logger.info(
            "budget.validate",
            total=total,
            budget=request.budget_usd,
            overage=overage,
            within=within,
        )

        if within:
            return BudgetValidation(
                is_within_budget=True,
                total_cost_usd=total,
                budget_usd=request.budget_usd,
                overage_usd=0.0,
                feedback=[],
            )

        feedback = await self._generate_feedback(request, itinerary, overage)
        return BudgetValidation(
            is_within_budget=False,
            total_cost_usd=total,
            budget_usd=request.budget_usd,
            overage_usd=overage,
            feedback=feedback,
        )

    async def _generate_feedback(
        self, request: TripRequest, itinerary: Itinerary, overage: float
    ) -> list[str]:
        baseline_total = estimate_baseline_total(
            request.destination, request.days, request.party_size, request.travel_style
        )
        baseline_day = baseline_per_day(request.destination, request.travel_style)

        user = (
            f"Trip budget: ${request.budget_usd:.2f}\n"
            f"Current total: ${self._sum_items(itinerary):.2f}\n"
            f"Overage: ${overage:.2f}\n"
            f"Pricing baseline for this destination/style: "
            f"~${baseline_day:.0f}/day per traveler "
            f"(~${baseline_total:.0f} total expected).\n\n"
            f"Itinerary:\n{itinerary.model_dump_json(indent=2)}"
        )
        data = await self._llm.chat_json(
            system_prompt=_SYSTEM_PROMPT, user_prompt=user, temperature=0.4
        )
        feedback = data.get("feedback", [])
        if not isinstance(feedback, list):
            logger.warning("budget.feedback.malformed", got=type(feedback).__name__)
            return ["Reduce overall costs to fit the budget."]
        return [str(x) for x in feedback if str(x).strip()]
