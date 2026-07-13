"""Assembles the ticket-handling graph and its per-task subgraph."""

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from langchain_openrouter import ChatOpenRouter

from storekeeper.config import load_classifier_settings
from storekeeper.graph.nodes import (
    await_approval_node,
    escalate_ticket_node,
    make_answer_policy_question_node,
    make_classify_node,
    make_draft_reply_node,
    make_execute_action_node,
    make_lookup_order_node,
    policy_gate_node,
    record_human_rejection_node,
    record_policy_denial_node,
    route_after_classify,
    route_after_gate,
    route_after_lookup,
)
from storekeeper.graph.state import TaskState, TicketState
from storekeeper.shopify.client import ShopifyClient


def build_task_pipeline_graph(shopify_client: ShopifyClient | None) -> CompiledStateGraph:
    """The guarded per-task pipeline: lookup -> gate -> approval -> execute.

    Compiled without its own checkpointer; it inherits the parent graph's
    checkpointer through the config it is invoked with.
    """
    task_builder = StateGraph(TaskState)
    task_builder.add_node("lookup_order", make_lookup_order_node(shopify_client))
    task_builder.add_node("policy_gate", policy_gate_node)
    task_builder.add_node("await_approval", await_approval_node)
    task_builder.add_node("execute_action", make_execute_action_node(shopify_client))
    task_builder.add_node("record_policy_denial", record_policy_denial_node)
    task_builder.add_node("record_human_rejection", record_human_rejection_node)

    task_builder.add_edge(START, "lookup_order")
    task_builder.add_conditional_edges("lookup_order", route_after_lookup, ["policy_gate", END])
    task_builder.add_conditional_edges(
        "policy_gate", route_after_gate, ["await_approval", "record_policy_denial"]
    )
    # await_approval routes itself via Command: execute_action or record_human_rejection.
    task_builder.add_edge("execute_action", END)
    task_builder.add_edge("record_policy_denial", END)
    task_builder.add_edge("record_human_rejection", END)
    return task_builder.compile()


def build_ticket_graph(
    *,
    checkpointer: BaseCheckpointSaver,
    classifier_model: BaseChatModel | None = None,
    draft_model: BaseChatModel | None = None,
    answer_model: BaseChatModel | None = None,
    shopify_client: ShopifyClient | None = None,
) -> CompiledStateGraph:
    """The ticket-level graph: classify, then run / answer / escalate, then draft."""
    if draft_model is None:
        # The drafter reuses the classifier's OpenRouter model for now.
        classifier_settings = load_classifier_settings()
        draft_model = ChatOpenRouter(model=classifier_settings.openrouter_model)
    if answer_model is None:
        answer_model = draft_model

    task_pipeline_graph = build_task_pipeline_graph(shopify_client)

    def run_task_pipeline(state: TicketState, config: RunnableConfig) -> dict:
        # This wrapper re-runs whenever the approval interrupt inside the
        # subgraph resumes, so it must stay free of side effects.
        single_task = state["tasks"][0]
        task_output = task_pipeline_graph.invoke(
            {
                "task": single_task,
                "shopify_order": None,
                "gate_verdict": None,
                "task_result": None,
            },
            config,
        )
        return {"task_results": [task_output["task_result"]]}

    ticket_builder = StateGraph(TicketState)
    ticket_builder.add_node("classify", make_classify_node(classifier_model))
    ticket_builder.add_node("run_task_pipeline", run_task_pipeline)
    ticket_builder.add_node("answer_policy_question", make_answer_policy_question_node(answer_model))
    ticket_builder.add_node("escalate_ticket", escalate_ticket_node)
    ticket_builder.add_node("draft_reply", make_draft_reply_node(draft_model))

    ticket_builder.add_edge(START, "classify")
    ticket_builder.add_conditional_edges(
        "classify",
        route_after_classify,
        ["run_task_pipeline", "answer_policy_question", "escalate_ticket"],
    )
    ticket_builder.add_edge("run_task_pipeline", "draft_reply")
    ticket_builder.add_edge("answer_policy_question", "draft_reply")
    ticket_builder.add_edge("escalate_ticket", END)
    ticket_builder.add_edge("draft_reply", END)
    return ticket_builder.compile(checkpointer=checkpointer)
