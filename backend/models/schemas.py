"""
Pydantic schemas for the planning workflow.
"""
from __future__ import annotations

from datetime import date
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


# --- Enums ---------------------------------------------------------------


class TravelStyle(str, Enum):
    BUDGET = "budget"
    MID = "mid"
    LUXURY = "luxury"


class ItemCategory(str, Enum):
    LODGING = "lodging"
    FOOD = "food"
    ACTIVITY = "activity"
    TRANSPORT = "transport"
    OTHER = "other"


class PlanStatus(str, Enum):
    APPROVED = "approved"
    BUDGET_EXCEEDED = "budget_exceeded"
    FAILED = "failed"


# --- Request -------------------------------------------------------------


class TripRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    destination: str = Field(..., min_length=2, max_length=120)
    start_date: date
    end_date: date
    budget_usd: float = Field(..., gt=0)
    travel_style: TravelStyle = TravelStyle.MID
    party_size: int = Field(1, ge=1, le=20)
    interests: list[str] = Field(default_factory=list)
    notes: str | None = Field(None, max_length=1000)

    @model_validator(mode="after")
    def _check_dates(self) -> "TripRequest":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self

    @property
    def days(self) -> int:
        return (self.end_date - self.start_date).days + 1


# --- Itinerary -----------------------------------------------------------


class ItineraryItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str
    description: str
    category: ItemCategory = ItemCategory.OTHER
    estimated_cost_usd: float = Field(..., ge=0)


class ItineraryDay(BaseModel):
    model_config = ConfigDict(extra="ignore")

    day_number: int = Field(..., ge=1)
    date: date
    items: list[ItineraryItem]

    @property
    def subtotal_usd(self) -> float:
        return round(sum(i.estimated_cost_usd for i in self.items), 2)


class Itinerary(BaseModel):
    model_config = ConfigDict(extra="ignore")

    destination: str
    summary: str
    days: list[ItineraryDay]
    total_estimated_cost_usd: float = Field(..., ge=0)
    currency: str = "USD"


# --- Budget --------------------------------------------------------------


class BudgetValidation(BaseModel):
    is_within_budget: bool
    total_cost_usd: float
    budget_usd: float
    overage_usd: float = 0.0
    feedback: list[str] = Field(default_factory=list)


# --- Response ------------------------------------------------------------


class PlanResponse(BaseModel):
    trip_id: UUID
    status: PlanStatus
    iterations: int
    itinerary: Itinerary
    validation: BudgetValidation


class PlanRecord(BaseModel):
    """DB row projection — what GET /trips/{id} returns."""

    trip_id: UUID
    status: PlanStatus
    iterations: int
    request: TripRequest
    itinerary: Itinerary
    validation: BudgetValidation
    created_at: str
