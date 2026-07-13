"""Ticket classification: turns customer text into validated domain Tasks."""

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openrouter import ChatOpenRouter
from pydantic import BaseModel, Field

from storekeeper.config import load_classifier_settings
from storekeeper.domain import Intent, RequestedAction, Task

# The policy gate consumes requested_action, but its value follows mechanically
# from the intent, so code derives it here. The model is never asked to pick an
# action — one less thing a ticket can talk the system into.
INTENT_TO_REQUESTED_ACTION: dict[Intent, RequestedAction | None] = {
    "cancel_order": "cancel_order",
    "refund_request": "issue_refund",
    "address_change": "update_shipping_address",
    "policy_question": None,
    "other": None,
}

CLASSIFIER_SYSTEM_PROMPT = """\
You classify customer support tickets for a Shopify store.

Read the customer's message and extract every distinct request as a task.

Intents:
- cancel_order: the customer wants an order cancelled.
- refund_request: the customer wants money back for an order (refund or return).
- address_change: the customer wants the shipping address on an order changed.
- policy_question: the customer asks about store policy (returns, shipping,
  warranty) without asking for an action on a specific order.
- other: anything that fits none of the intents above, or is too unclear to
  classify.

Rules:
- Create one task per distinct request; most tickets contain exactly one.
- Copy the order reference exactly as the customer wrote it, keeping the
  leading #. Use null when the request names no specific order.
- Never invent an order reference that is not in the message.
- Confidence is your certainty in the chosen intent, from 0.0 to 1.0. Use a
  low value when the message is ambiguous.
"""


class ClassifiedTask(BaseModel):
    """One customer request extracted from a support ticket."""

    intent: Intent = Field(
        description="The kind of request the customer is making."
    )
    order_reference: str | None = Field(
        description=(
            "The order number exactly as the customer wrote it, for example "
            "'#1036'. Null when the request names no specific order."
        )
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Certainty in the chosen intent, from 0.0 to 1.0.",
    )


class TicketClassification(BaseModel):
    """Every distinct customer request found in one ticket."""

    tasks: list[ClassifiedTask] = Field(
        description=(
            "One entry per distinct request in the ticket, in the order the "
            "requests appear."
        )
    )


def convert_classification_to_tasks(classification: TicketClassification) -> list[Task]:
    domain_tasks: list[Task] = []
    for classified_task in classification.tasks:
        domain_tasks.append(
            Task(
                intent=classified_task.intent,
                order_reference=classified_task.order_reference,
                requested_action=INTENT_TO_REQUESTED_ACTION[classified_task.intent],
                confidence=classified_task.confidence,
            )
        )
    return domain_tasks


def classify_ticket(ticket_text: str, classifier_model: BaseChatModel | None = None) -> list[Task]:
    if not ticket_text.strip():
        raise ValueError("Ticket text cannot be empty.")

    if classifier_model is None:
        classifier_settings = load_classifier_settings()
        classifier_model = ChatOpenRouter(model=classifier_settings.openrouter_model)

    structured_classifier = classifier_model.with_structured_output(TicketClassification)
    classification = structured_classifier.invoke(
        [
            SystemMessage(content=CLASSIFIER_SYSTEM_PROMPT),
            HumanMessage(content=ticket_text),
        ]
    )
    return convert_classification_to_tasks(classification)
