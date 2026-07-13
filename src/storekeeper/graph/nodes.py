"""Node functions and routing rules for the ticket graph.

Routing decisions live in plain Python route functions. The LLM classifies
and drafts; it never chooses which node runs next.
"""

import json
from datetime import datetime, timezone
from typing import Callable, Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END
from langgraph.types import Command, interrupt
from pydantic import BaseModel, Field

from storekeeper.classify import classify_ticket
from storekeeper.domain import Task, TaskOutcome, TaskResult
from storekeeper.graph.state import TaskState, TicketState
from storekeeper.policy.gate import policy_gate
from storekeeper.policy_docs import find_policy_context, format_policy_extracts
from storekeeper.shopify.client import ShopifyClient
from storekeeper.shopify.operations import (
    InvalidOrderReferenceError,
    OrderNotFoundError,
    lookup_order,
)
from storekeeper.shopify.writes import cancel_order, issue_full_refund

REPLY_DRAFT_SYSTEM_PROMPT = """\
You draft replies to customer support tickets for a Shopify store.

You receive the customer's message and structured task results describing what
the system did or decided. Write a short, warm, professional reply.

Rules:
- State only what the task results say. Never promise anything beyond them.
- Outcome "executed": confirm the action was completed.
- Outcome "denied_by_policy": explain the denial using the gate reason; when
  store policy text is provided, refer to the policy naturally.
- Outcome "rejected_by_human": say the request was reviewed and declined.
- Outcome "failed": apologize and ask the customer to double-check the details
  they gave, such as the order number.
- Outcome "answered": relay the provided answer faithfully; do not add policy
  claims that are not in it.
- Do not invent order details, amounts, dates, or policy that are not in the input.
- Sign off as "The Support Team".
"""

POLICY_ANSWER_SYSTEM_PROMPT = """\
You answer customer questions about store policy for a Shopify store.

You receive the customer's message and the store's policy documents. Answer
using only what the documents say.

Rules:
- If the documents do not cover the question, say so and tell the customer a
  team member will follow up. Never invent policy.
- Keep the answer short and factual.
- In cited_documents, list the file name of every document you used.
"""


class PolicyAnswer(BaseModel):
    """A policy answer plus the documents that back it."""

    answer: str = Field(
        description="The answer to the customer's question, based only on the policy documents."
    )
    cited_documents: list[str] = Field(
        description="File names of the policy documents the answer is based on."
    )


# --- Ticket-level nodes -----------------------------------------------------


def make_classify_node(classifier_model: BaseChatModel | None) -> Callable:
    def classify_node(state: TicketState) -> dict:
        return {"tasks": classify_ticket(state["ticket_text"], classifier_model=classifier_model)}

    return classify_node


def route_after_classify(
    state: TicketState,
) -> Literal["run_task_pipeline", "answer_policy_question", "escalate_ticket"]:
    tasks = state["tasks"]
    if len(tasks) != 1:
        return "escalate_ticket"
    single_task = tasks[0]
    if single_task["intent"] == "policy_question":
        return "answer_policy_question"
    # "other" tickets have no automated path; a human reads them.
    if single_task["requested_action"] is None:
        return "escalate_ticket"
    # The classifier does not extract the new address yet (slice 5c), so a
    # human performs address changes.
    if single_task["intent"] == "address_change":
        return "escalate_ticket"
    if not single_task["order_reference"]:
        return "escalate_ticket"
    return "run_task_pipeline"


def escalate_ticket_node(state: TicketState) -> dict:
    return {
        "ticket_outcome": "escalated_to_human",
        "escalation_reason": describe_escalation_reason(state["tasks"]),
    }


def describe_escalation_reason(tasks: list[Task]) -> str:
    if len(tasks) == 0:
        return "The classifier found no request in the ticket."
    if len(tasks) > 1:
        return "The ticket contains multiple requests; v1 handles one per ticket."
    single_task = tasks[0]
    if single_task["requested_action"] is None:
        return f"Intent '{single_task['intent']}' has no automated handling yet."
    if single_task["intent"] == "address_change":
        return "Address changes are not automated yet; update the address by hand."
    return "The request names no order."


def make_answer_policy_question_node(answer_model: BaseChatModel) -> Callable:
    def answer_policy_question_node(state: TicketState) -> dict:
        question_task = state["tasks"][0]
        policy_extracts = find_policy_context(question_task)
        structured_answerer = answer_model.with_structured_output(PolicyAnswer)
        policy_answer = structured_answerer.invoke(
            [
                SystemMessage(content=POLICY_ANSWER_SYSTEM_PROMPT),
                HumanMessage(
                    content=(
                        f"Customer question:\n{state['ticket_text']}\n\n"
                        f"Policy documents:\n{format_policy_extracts(policy_extracts)}"
                    )
                ),
            ]
        )
        # Keep only citations naming documents we actually provided.
        provided_document_names = {extract["document_name"] for extract in policy_extracts}
        verified_citations = [
            document_name
            for document_name in policy_answer.cited_documents
            if document_name in provided_document_names
        ]
        answered_task_result: TaskResult = {
            "task": question_task,
            "outcome": "answered",
            "gate_verdict": None,
            "action_result": {"answer": policy_answer.answer},
            "policy_citations": verified_citations,
        }
        return {"task_results": [answered_task_result]}

    return answer_policy_question_node


def make_draft_reply_node(draft_model: BaseChatModel) -> Callable:
    def draft_reply_node(state: TicketState) -> dict:
        # default=str renders Decimal amounts and datetimes readably.
        task_results_json = json.dumps(state["task_results"], indent=2, default=str)

        # Denied requests get the relevant policy text so the reply can cite
        # store policy instead of just the gate's one-line reason.
        denied_task_results = [
            task_result
            for task_result in state["task_results"]
            if task_result["outcome"] == "denied_by_policy"
        ]
        policy_reference_block = ""
        if denied_task_results:
            policy_extracts = find_policy_context(denied_task_results[0]["task"])
            policy_reference_block = (
                f"\n\nStore policy for reference:\n{format_policy_extracts(policy_extracts)}"
            )

        response = draft_model.invoke(
            [
                SystemMessage(content=REPLY_DRAFT_SYSTEM_PROMPT),
                HumanMessage(
                    content=(
                        f"Customer message:\n{state['ticket_text']}\n\n"
                        f"Task results:\n{task_results_json}"
                        f"{policy_reference_block}"
                    )
                ),
            ]
        )
        return {"reply_draft": response.content, "ticket_outcome": "resolved"}

    return draft_reply_node


# --- Task-pipeline nodes ------------------------------------------------------


def make_lookup_order_node(shopify_client: ShopifyClient | None) -> Callable:
    def lookup_order_node(state: TaskState) -> dict:
        # lookup_order validates and normalizes the customer-written reference
        # itself; a hostile or garbled reference fails softly here, never
        # reaching the gate or an approval.
        try:
            shopify_order = lookup_order(state["task"]["order_reference"], client=shopify_client)
        except (InvalidOrderReferenceError, OrderNotFoundError):
            return {"task_result": build_task_result(state, outcome="failed")}
        return {"shopify_order": shopify_order}

    return lookup_order_node


def route_after_lookup(state: TaskState) -> Literal["policy_gate", "__end__"]:
    if state.get("task_result") is not None:
        return END
    return "policy_gate"


def policy_gate_node(state: TaskState) -> dict:
    requested_action = state["task"]["requested_action"]
    shopify_order = state["shopify_order"]
    # Routing guarantees an action and a fetched order before this node runs.
    assert requested_action is not None and shopify_order is not None
    gate_verdict = policy_gate(
        requested_action,
        shopify_order["facts"],
        evaluated_at=datetime.now(timezone.utc),
    )
    return {"gate_verdict": gate_verdict}


def route_after_gate(state: TaskState) -> Literal["await_approval", "record_policy_denial"]:
    gate_verdict = state["gate_verdict"]
    # This route only runs after the gate node has written its verdict.
    assert gate_verdict is not None
    if gate_verdict["passed"]:
        return "await_approval"
    return "record_policy_denial"


def await_approval_node(state: TaskState) -> Command[Literal["execute_action", "record_human_rejection"]]:
    shopify_order = state["shopify_order"]
    gate_verdict = state["gate_verdict"]
    # Only the gate's passing edge leads here, so both are always present.
    assert shopify_order is not None and gate_verdict is not None
    order_facts = shopify_order["facts"]
    # The payload must be JSON-serializable, so the Decimal amount becomes text.
    decision = interrupt(
        {
            "question": "Approve this action?",
            "action": state["task"]["requested_action"],
            "order": shopify_order["name"],
            # What the customer actually wrote, so the approver can audit the
            # request-to-order binding, not just the selected order.
            "requested_reference": state["task"]["order_reference"],
            "amount": f"{order_facts['total_amount']} {order_facts['currency_code']}",
            "gate_rule": gate_verdict["rule"],
            "flags": gate_verdict["flags"],
        }
    )
    if decision == "approve":
        return Command(goto="execute_action")
    return Command(goto="record_human_rejection")


def make_execute_action_node(shopify_client: ShopifyClient | None) -> Callable:
    def execute_action_node(state: TaskState) -> dict:
        requested_action = state["task"]["requested_action"]
        shopify_order = state["shopify_order"]
        # Execution is only reachable through lookup, gate, and approval.
        assert shopify_order is not None
        shopify_order_id = shopify_order["id"]
        if requested_action == "cancel_order":
            action_result = cancel_order(shopify_order_id, client=shopify_client)
        elif requested_action == "issue_refund":
            action_result = issue_full_refund(shopify_order_id, client=shopify_client)
        else:
            # Address changes escalate at classification; reaching here means
            # the routing and this node disagree about what is executable.
            raise ValueError(f"No write operation wired for action: {requested_action}")
        return {"task_result": build_task_result(state, outcome="executed", action_result=action_result)}

    return execute_action_node


def record_policy_denial_node(state: TaskState) -> dict:
    relevant_policy_names = [
        extract["document_name"] for extract in find_policy_context(state["task"])
    ]
    return {
        "task_result": build_task_result(
            state, outcome="denied_by_policy", policy_citations=relevant_policy_names
        )
    }


def record_human_rejection_node(state: TaskState) -> dict:
    return {"task_result": build_task_result(state, outcome="rejected_by_human")}


def build_task_result(
    state: TaskState,
    outcome: TaskOutcome,
    action_result: dict | None = None,
    policy_citations: list[str] | None = None,
) -> TaskResult:
    return {
        "task": state["task"],
        "outcome": outcome,
        "gate_verdict": state.get("gate_verdict"),
        "action_result": action_result,
        "policy_citations": policy_citations if policy_citations is not None else [],
    }
