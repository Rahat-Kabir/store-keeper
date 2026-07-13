# As-built technical specification

## Domain contracts

`src/storekeeper/domain.py` owns shared `Task`, `ShippingAddress`, `OrderFacts`,
`GateVerdict`, and `TaskResult` types. `OrderFacts` is a small normalized view
of a Shopify order. `Task.order_reference` holds the order name as the customer
wrote it (e.g. `#1036`), not the Shopify GraphQL id. Address-change tasks carry
the customer-provided address fields in `Task.new_shipping_address`.

## Ticket classifier

`classify.classify_ticket(ticket_text)` turns a customer message into domain
`Task`s using LangChain structured output on `ChatOpenRouter`. The model slug
comes from the `OPENROUTER_MODEL` env variable.

- A Pydantic schema (`TicketClassification`) validates the LLM output before
  any other code sees it; intent values reuse the `Intent` literal from
  `domain.py`, so allowed values have one source of truth.
- The model picks only the intent. `requested_action` is derived in code from
  a fixed intent→action mapping, so the model cannot emit an inconsistent
  intent/action pair.
- For address changes, the model extracts structured address fields but must
  leave omitted fields null. Automation requires street, city, state or
  province, postal code, and country; incomplete requests escalate instead of
  guessing.
- Output is a list of tasks even in v1: multi-request tickets classify into
  one task per request, in ticket order. This is where the v2 planner plugs in.
- Tests inject a fake model; the unit suite makes no network calls.

## Policy corpus and answering

- `policies/` (repo root) holds short markdown store-policy documents. Their
  numbers must match the gate's constants (30-day refunds, $100 high-value
  threshold) — the gate decides, the docs explain.
- `policy_docs.find_policy_context(task, ticket_text)` is the retrieval seam.
  Action intents still map deterministically to their whole policy document.
  Policy questions with ticket text query the top three heading chunks from a
  persistent Chroma collection in `var/policy_index/`; calling without ticket
  text keeps the whole-corpus fallback for compatibility. The collection uses
  Chroma's local ONNX `all-MiniLM-L6-v2` embedding function and cosine distance,
  so indexing and retrieval need no API key. Policy text feeds the answering
  and drafting LLMs only — never the gate.
- `scripts/index_policies.py` rebuilds the collection from `policies/*.md`.
  Each `##` section becomes one chunk containing the document title, heading,
  and body, with source filename and heading metadata. Run it after changing a
  policy document. `scripts/search_policy.py` prints the nearest three chunks
  and their cosine distances so retrieval quality can be checked before graph
  use.
- `answer_policy_question` (ticket-level node) answers with structured output
  (`PolicyAnswer`); citations are kept only if they name documents that were
  actually provided. The result is a `TaskResult` with outcome `"answered"`
  and `policy_citations`; `draft_reply` remains the single reply author.
- Denied actions carry the relevant document names in `policy_citations`, and
  the drafter receives the policy text so replies cite store policy.

## Ticket registry

`tickets.py` maintains a small SQLite registry at `var/tickets.sqlite` with a
ticket id, its original text, and creation time. The registry is only the
listing index for the CLI and future API; it does not duplicate workflow state.
`get_ticket_status()` reads the ticket's LangGraph checkpoint and derives
`pending_approval`, `resolved`, or `not_found` from the saved values and
interrupts. Starting a new CLI ticket refuses an id already present in either
the registry or the checkpoint database, while approval resumes keep using the
existing id.

## Operator API

`api/app.py` owns a FastAPI application factory and four synchronous routes:
`POST /api/tickets`, `GET /api/tickets`, `GET /api/tickets/{ticket_id}`, and
`POST /api/tickets/{ticket_id}/decision`. The application lifecycle opens the
shared SQLite checkpointer and compiles the existing graph once. Tests inject a
stub graph through the same factory.

`api/schemas.py` defines the public Pydantic request and response contracts.
Responses mirror ticket state, task results, and the approval interrupt rather
than returning raw checkpoint objects. Duplicate ids and decisions on tickets
that are not pending return 409; unknown registry ids return 404. Endpoints use
plain `def` because graph, model, Shopify, and SQLite operations are synchronous.
The API never calls Shopify, the classifier, or the drafter directly.

## Operator console

`frontend/` is a Vite + React + TypeScript single-page application. In
development, Vite runs on `127.0.0.1:5173` and proxies `/api` to FastAPI on
`127.0.0.1:8000`, so no CORS configuration is needed. It uses plain `fetch`
and mirrors the Pydantic response fields with TypeScript interfaces.

`App.tsx` owns ticket selection, list refresh, and new-ticket mode.
`TicketList`, `TicketForm`, and `TicketDetail` render the two-column console:
newest-first history on the left and the selected customer message, outcome,
reply draft, and verified citations on the right. Detailed outcome badges are
derived from the selected ticket's `task_results`; unselected list rows use
the checkpoint-derived summary status. Pending tickets are displayed safely,
but approval details and decision controls remain for slice 8.3.

## Ticket graph

`graph/build.py` assembles two LangGraph `StateGraph`s:

- **Ticket graph** (`TicketState`): `classify` → route → `run_task_pipeline`,
  `answer_policy_question`, or `escalate_ticket` → `draft_reply`. Escalation
  paths: multiple requests, intent `other`, no order reference, or an incomplete
  address-change request.
- **Task pipeline subgraph** (`TaskState`): `lookup_order` → `policy_gate` →
  route → `await_approval` (denied requests skip straight to a result). The
  subgraph is invoked by a side-effect-free wrapper node — the v2 planner will
  fan out to this same subgraph via `Send`.

Rules of the graph:

- All routing is plain Python route functions reading state; the LLM never
  chooses an edge. There is no path to `execute_action` that bypasses
  `policy_gate` and `await_approval`.
- `await_approval` calls `interrupt()` with a JSON-safe payload and routes the
  decision with `Command(goto=...)`. Resume values: `"approve"` / `"reject"`.
- Checkpoints persist in `var/checkpoints.sqlite` (`SqliteSaver`);
  `thread_id` is the ticket id, so an approval survives process restarts.
- `execute_action` runs real writes from `shopify/writes.py`: `cancel_order`
  (async `orderCancel`; refunds the original payment and restocks) and
  `issue_full_refund` (`order.suggestedRefund` decides which payment
  transactions to reverse; orders without captured payments get their items
  marked refunded), plus `update_shipping_address` (`orderUpdate`). Address
  updates preserve the current recipient name, company, and phone when the
  customer omits them, while replacing the delivery-location fields. The
  approval payload shows both current and final addresses. `refundCreate`
  carries an order-derived `@idempotent` key, so a re-executed node cannot
  refund twice.
  Note: `orderCancel` returning a job id means Shopify *accepted* the
  cancellation; completion happens asynchronously on Shopify's side.

## What leaves the machine

- **OpenRouter** receives ticket text (classification, drafting), policy
  document text and questions (answering), and structured task results
  including order names and amounts (drafting).
- **LangSmith** (when `LANGSMITH_TRACING=true`) receives full run traces:
  prompts, ticket text, order data, and drafted replies.
- **`var/checkpoints.sqlite`** retains every ticket's state — text, order
  facts, decisions, replies — locally and indefinitely. Keep it private.
- **Shopify** receives only order lookups and approved write mutations; ticket
  text itself is never sent to Shopify.
- A missing order becomes outcome `failed` and an apologetic reply draft.
- `draft_reply` is an LLM call over the structured `task_results` list;
  promoting it to the v2 composer is a prompt change.

## Policy gate

`shopify.operations.lookup_order()` reads an order by name and converts Shopify's
response into `OrderFacts`. Any status except `UNFULFILLED` is treated as fulfilled.

Order binding is strict, because the reference comes from ticket text:

- A reference must normalize to `#` + digits (allowlist — anything else raises
  `InvalidOrderReferenceError` before any Shopify call).
- The returned order's name must equal the normalized reference exactly, or
  the order is treated as not found. An action can never bind to an order the
  customer did not name.
- The approval payload carries the customer-written reference alongside the
  resolved order name, so the human approves the binding, not just the result.

`policy_gate(requested_action, order_facts, evaluated_at)` is deterministic and
has no Shopify, LLM, or graph dependency.

- Cancellation and address changes require an unfulfilled order.
- Refunds require `processedAt` to be 30 days old or less.
- Refunds over 100 store-currency units receive a `high_value` flag.
- Passing a rule means eligible for later human approval, not execution.
