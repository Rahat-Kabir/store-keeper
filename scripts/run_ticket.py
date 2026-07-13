"""Run one support ticket through the guarded pipeline, or resume a paused one."""

import argparse
import json
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from storekeeper.graph.build import build_ticket_graph

CHECKPOINT_DATABASE_PATH = Path("var/checkpoints.sqlite")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("ticket_id", help="Stable id for this ticket; also the handle used to resume it")
    parser.add_argument("ticket_text", nargs="?", help="The customer's message, quoted (omit when resuming)")
    decision_group = parser.add_mutually_exclusive_group()
    decision_group.add_argument("--approve", action="store_true", help="Approve the pending action")
    decision_group.add_argument("--reject", action="store_true", help="Reject the pending action")
    arguments = parser.parse_args()

    resuming = arguments.approve or arguments.reject
    if resuming and arguments.ticket_text:
        parser.error("Pass either ticket text or a decision flag, not both.")
    if not resuming and not arguments.ticket_text:
        parser.error("A new ticket needs ticket text; resuming needs --approve or --reject.")

    CHECKPOINT_DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    config = {"configurable": {"thread_id": arguments.ticket_id}}

    with SqliteSaver.from_conn_string(str(CHECKPOINT_DATABASE_PATH)) as checkpointer:
        ticket_graph = build_ticket_graph(checkpointer=checkpointer)
        if resuming:
            decision = "approve" if arguments.approve else "reject"
            result = ticket_graph.invoke(Command(resume=decision), config)
        else:
            result = ticket_graph.invoke(
                {
                    "ticket_text": arguments.ticket_text,
                    "tasks": [],
                    "task_results": [],
                    "reply_draft": None,
                    "ticket_outcome": None,
                    "escalation_reason": None,
                },
                config,
            )
        print_result(arguments.ticket_id, result)


def print_result(ticket_id: str, result: dict) -> None:
    if "__interrupt__" in result:
        pending_approval = result["__interrupt__"][0].value
        print(f"== AWAITING APPROVAL -- ticket {ticket_id} ==")
        print(f"  Action: {pending_approval['action']} on order {pending_approval['order']}")
        print(f"  Customer wrote: \"{pending_approval['requested_reference']}\"")
        print(f"  Amount: {pending_approval['amount']}")
        print(f"  Gate:   passed ({pending_approval['gate_rule']})")
        if pending_approval["new_shipping_address"] is not None:
            print(
                "  Current address: "
                f"{json.dumps(pending_approval['current_shipping_address'], ensure_ascii=False)}"
            )
            print(
                "  New address:     "
                f"{json.dumps(pending_approval['new_shipping_address'], ensure_ascii=False)}"
            )
        if pending_approval["flags"]:
            print(f"  Flags:  {', '.join(pending_approval['flags'])}")
        print()
        print(f"  To decide:  run_ticket.py {ticket_id} --approve   or   --reject")
        return

    print(f"== Ticket {ticket_id}: {result['ticket_outcome']} ==")
    if result["ticket_outcome"] == "escalated_to_human":
        print(f"  Reason: {result['escalation_reason']}")
        return

    final_task_result = result["task_results"][-1]
    print(f"  Task outcome: {final_task_result['outcome']}")
    action_result = final_task_result["action_result"]
    if action_result and action_result.get("summary"):
        print(f"  Action: {action_result['summary']}")
    if final_task_result["policy_citations"]:
        print(f"  Policy cited: {', '.join(final_task_result['policy_citations'])}")
    print()
    print("  Reply draft:")
    for draft_line in result["reply_draft"].splitlines():
        print(f"    {draft_line}")


if __name__ == "__main__":
    main()
