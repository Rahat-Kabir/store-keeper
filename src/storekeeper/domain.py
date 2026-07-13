"""Shared business data contracts."""

from datetime import datetime
from decimal import Decimal
from typing import Literal, TypedDict

Intent = Literal[
    "cancel_order",
    "refund_request",
    "address_change",
    "policy_question",
    "other",
]

RequestedAction = Literal[
    "cancel_order",
    "issue_refund",
    "update_shipping_address",
]

TaskOutcome = Literal[
    "executed",
    "rejected_by_human",
    "denied_by_policy",
    "answered",
    "failed",
]


class Task(TypedDict):
    intent: Intent
    # The order reference as the customer wrote it (e.g. "#1036"), which is a
    # Shopify order *name* — not the Shopify GraphQL id (ShopifyOrder["id"]).
    order_reference: str | None
    requested_action: RequestedAction | None
    confidence: float


class OrderFacts(TypedDict):
    """Only the Shopify order fields that policy rules need."""

    processed_at: datetime
    fulfilled: bool
    total_amount: Decimal
    currency_code: str


class ShopifyOrder(TypedDict):
    id: str
    name: str
    facts: OrderFacts


class GateVerdict(TypedDict):
    passed: bool
    rule: str
    reason: str
    flags: list[str]


class TaskResult(TypedDict):
    task: Task
    outcome: TaskOutcome
    gate_verdict: GateVerdict | None
    action_result: dict | None
    policy_citations: list[str]
