"""Validated request and response models for the operator API."""

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StringConstraints

from storekeeper.domain import Intent, RequestedAction, TaskOutcome
from storekeeper.graph.state import TicketOutcome
from storekeeper.tickets import TicketStatus

NonEmptyText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]


class CreateTicketRequest(BaseModel):
    ticket_text: NonEmptyText
    ticket_id: NonEmptyText | None = None


class TicketDecisionRequest(BaseModel):
    decision: Literal["approve", "reject"]


class ShippingAddressResponse(BaseModel):
    first_name: str | None
    last_name: str | None
    company: str | None
    address1: str | None
    address2: str | None
    city: str | None
    province: str | None
    zip: str | None
    country: str | None
    phone: str | None


class TaskResponse(BaseModel):
    intent: Intent
    order_reference: str | None
    requested_action: RequestedAction | None
    new_shipping_address: ShippingAddressResponse | None
    confidence: float


class GateVerdictResponse(BaseModel):
    passed: bool
    rule: str
    reason: str
    flags: list[str] = Field(default_factory=list)


class TaskResultResponse(BaseModel):
    task: TaskResponse
    outcome: TaskOutcome
    gate_verdict: GateVerdictResponse | None
    action_result: dict[str, Any] | None
    policy_citations: list[str] = Field(default_factory=list)


class ApprovalPayloadResponse(BaseModel):
    question: str
    action: RequestedAction
    order: str
    requested_reference: str | None
    amount: str
    gate_rule: str
    gate_reason: str
    flags: list[str] = Field(default_factory=list)
    current_shipping_address: ShippingAddressResponse | None
    new_shipping_address: ShippingAddressResponse | None


class TicketSummaryResponse(BaseModel):
    ticket_id: str
    ticket_text: str
    created_at: datetime
    status: TicketStatus


class TicketDetailResponse(TicketSummaryResponse):
    pending_approval: ApprovalPayloadResponse | None
    tasks: list[TaskResponse] = Field(default_factory=list)
    task_results: list[TaskResultResponse] = Field(default_factory=list)
    reply_draft: str | None
    ticket_outcome: TicketOutcome | None
    escalation_reason: str | None
