"""FastAPI wrapper around the existing ticket graph."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    HTTPException,
    Path as PathParameter,
    Request,
)
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command, StateSnapshot

from storekeeper.api.schemas import (
    ApprovalPayloadResponse,
    CreateTicketRequest,
    TicketDecisionRequest,
    TicketDetailResponse,
    TicketSummaryResponse,
)
from storekeeper.graph.build import build_ticket_graph
from storekeeper.tickets import (
    CHECKPOINT_DATABASE_PATH,
    TICKET_DATABASE_PATH,
    DuplicateTicketError,
    TicketRecord,
    create_ticket,
    derive_ticket_status,
    generate_ticket_id,
    get_ticket,
    get_ticket_status,
    list_tickets,
)

router = APIRouter(prefix="/api/tickets", tags=["tickets"])


def get_request_ticket_graph(request: Request) -> CompiledStateGraph:
    return request.app.state.ticket_graph


def get_request_ticket_database_path(request: Request) -> Path:
    return request.app.state.ticket_database_path


TicketGraphDependency = Annotated[CompiledStateGraph, Depends(get_request_ticket_graph)]
TicketDatabasePathDependency = Annotated[Path, Depends(get_request_ticket_database_path)]
TicketIdPath = Annotated[str, PathParameter(min_length=1)]


@router.post("", status_code=201)
def create_ticket_endpoint(
    request_body: CreateTicketRequest,
    ticket_graph: TicketGraphDependency,
    ticket_database_path: TicketDatabasePathDependency,
) -> TicketDetailResponse:
    ticket_id = request_body.ticket_id or generate_ticket_id()
    if get_ticket_status(ticket_id, ticket_graph) != "not_found":
        raise HTTPException(
            status_code=409,
            detail=f"Ticket id {ticket_id!r} already has saved graph state.",
        )

    try:
        ticket_record = create_ticket(
            ticket_id,
            request_body.ticket_text,
            database_path=ticket_database_path,
        )
    except DuplicateTicketError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    ticket_graph.invoke(
        {
            "ticket_text": ticket_record["ticket_text"],
            "tasks": [],
            "task_results": [],
            "reply_draft": None,
            "ticket_outcome": None,
            "escalation_reason": None,
        },
        _thread_config(ticket_id),
    )
    return _build_ticket_detail_response(ticket_record, ticket_graph)


@router.get("")
def list_tickets_endpoint(
    ticket_graph: TicketGraphDependency,
    ticket_database_path: TicketDatabasePathDependency,
) -> list[TicketSummaryResponse]:
    return [
        TicketSummaryResponse(
            **ticket_record,
            status=get_ticket_status(ticket_record["ticket_id"], ticket_graph),
        )
        for ticket_record in list_tickets(database_path=ticket_database_path)
    ]


@router.get("/{ticket_id}")
def get_ticket_endpoint(
    ticket_id: TicketIdPath,
    ticket_graph: TicketGraphDependency,
    ticket_database_path: TicketDatabasePathDependency,
) -> TicketDetailResponse:
    ticket_record = _require_ticket(ticket_id, ticket_database_path)
    return _build_ticket_detail_response(ticket_record, ticket_graph)


@router.post("/{ticket_id}/decision")
def decide_ticket_endpoint(
    ticket_id: TicketIdPath,
    request_body: TicketDecisionRequest,
    ticket_graph: TicketGraphDependency,
    ticket_database_path: TicketDatabasePathDependency,
) -> TicketDetailResponse:
    ticket_record = _require_ticket(ticket_id, ticket_database_path)
    if get_ticket_status(ticket_id, ticket_graph) != "pending_approval":
        raise HTTPException(
            status_code=409,
            detail=f"Ticket {ticket_id!r} is not awaiting approval.",
        )

    ticket_graph.invoke(
        Command(resume=request_body.decision),
        _thread_config(ticket_id),
    )
    return _build_ticket_detail_response(ticket_record, ticket_graph)


def create_app(
    *,
    ticket_graph: CompiledStateGraph | None = None,
    ticket_database_path: Path = TICKET_DATABASE_PATH,
    checkpoint_database_path: Path = CHECKPOINT_DATABASE_PATH,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        application.state.ticket_database_path = ticket_database_path
        if ticket_graph is not None:
            application.state.ticket_graph = ticket_graph
            yield
            return

        checkpoint_database_path.parent.mkdir(parents=True, exist_ok=True)
        with SqliteSaver.from_conn_string(str(checkpoint_database_path)) as checkpointer:
            application.state.ticket_graph = build_ticket_graph(checkpointer=checkpointer)
            yield

    application = FastAPI(title="storekeeper operator API", lifespan=lifespan)
    application.include_router(router)
    return application


def _require_ticket(ticket_id: str, ticket_database_path: Path) -> TicketRecord:
    ticket_record = get_ticket(ticket_id, database_path=ticket_database_path)
    if ticket_record is None:
        raise HTTPException(
            status_code=404,
            detail=f"Ticket {ticket_id!r} was not found.",
        )
    return ticket_record


def _build_ticket_detail_response(
    ticket_record: TicketRecord,
    ticket_graph: CompiledStateGraph,
) -> TicketDetailResponse:
    state_snapshot = ticket_graph.get_state(
        _thread_config(ticket_record["ticket_id"])
    )
    pending_approval = _get_pending_approval(state_snapshot)
    state_values = state_snapshot.values
    return TicketDetailResponse(
        **ticket_record,
        status=derive_ticket_status(state_snapshot),
        pending_approval=pending_approval,
        tasks=state_values.get("tasks", []),
        task_results=state_values.get("task_results", []),
        reply_draft=state_values.get("reply_draft"),
        ticket_outcome=state_values.get("ticket_outcome"),
        escalation_reason=state_values.get("escalation_reason"),
    )


def _get_pending_approval(
    state_snapshot: StateSnapshot,
) -> ApprovalPayloadResponse | None:
    if not state_snapshot.interrupts:
        return None
    return ApprovalPayloadResponse.model_validate(state_snapshot.interrupts[0].value)


def _thread_config(ticket_id: str) -> dict:
    return {"configurable": {"thread_id": ticket_id}}


app = create_app()
