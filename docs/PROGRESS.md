# Progress

Feature log: what's built, what's next. Details live in
[tech_spec.md](tech_spec.md) and [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## Roadmap

- [x] 1. Scaffold + Shopify client wrapper + smoke test
- [x] 2. Seed script — 50 live test orders across policy edge cases
- [x] 3. Domain contracts + pure policy gate + live policy-check CLI
- [x] 4. Ticket classifier (structured output, task list) + CLI
- [x] 5. LangGraph pipeline: approval interrupt, SQLite checkpoints, ticket CLI
- [x] 5b. Real Shopify writes: cancel + full refund behind approval
- [x] 6. Policy corpus + policy-question answering with verified citations
- [x] Hardening: strict order-reference binding
- [x] 6b. RAG behind `find_policy_context` (local Chroma, chunk by heading)
- [x] 5c. Address extraction in the classifier + `orderUpdate` write
- [x] 7a. Polish: LangSmith trace walkthrough (docs + README teaser image)
- [x] 8.0. Ticket registry + completed-id reuse guard
- [x] 8.1. FastAPI wrapper: create/list/detail/decision endpoints
- [ ] 8. Operator console: FastAPI API wrapping the graph (curl-proven first),
      then a Vite + React single-page UI with full CLI feature parity ← 8.2 next
- [ ] 7b. Polish: README GIF/screenshots of the operator console (after 8)
- [ ] Backlog: seed-script argparse, scope trim

## Log

### 1 — Shopify foundation (2026-07-12)

Env config and a single `ShopifyClient` (client-credentials auth, token
caching, one retry on 401). Smoke test passed against the live dev store.

### 2 — Seed data (2026-07-12)

Resumable seed script created 50 orders across happy / fulfilled / old /
high-value segments; reruns create only what's missing.

### 3 — Policy gate + live check (2026-07-12)

Shared domain contracts and a pure-Python gate: cancel and address changes
need an unfulfilled order, refunds need ≤ 30 days, over $100 gets flagged.
Live order lookup + `check_order_policy.py` CLI verified against real orders.

### 4 — Ticket classifier (2026-07-12)

LLM classification into a validated task list (Pydantic on `ChatOpenRouter`,
model slug from env). The model picks only the intent; the action is derived
in code. Proven live via `classify_ticket.py`.

### 5 — Guarded graph (2026-07-13)

LangGraph ticket graph wrapping a per-task subgraph; eligible writes pause at
a human-approval interrupt that survives process restarts (SQLite, thread_id
= ticket id). `run_ticket.py` runs, `--approve` / `--reject` resume. Replies
are LLM-drafted from structured results.

### 5b — Real writes (2026-07-13)

`orderCancel` and `suggestedRefund`-driven `refundCreate` (order-derived
idempotency key) run after approval; a rejected approval sends zero write
calls. Verified live: real cancellation and a real 42 USD refund.
Address changes still escalated here; slice 5c later automated them.

### 6 — Policy answers (2026-07-13)

`policies/` corpus (numbers locked as real policy: 30 days / $100) behind the
`find_policy_context()` seam. Policy questions get answered with citations
verified in code; denied requests cite the relevant policy in their reply.

### 6b — Policy RAG (2026-07-13)

Policy questions retrieve the top three heading chunks from a local Chroma
index using local MiniLM embeddings. Index and search CLIs prove retrieval
before graph use; action-denial citations still read deterministic whole docs.

### 5c — Shipping-address changes (2026-07-13)

The classifier extracts the requested address without inventing missing fields;
incomplete requests escalate. Eligible changes show current and final addresses
for human approval, then execute Shopify `orderUpdate`.

### 7a — LangSmith walkthrough (2026-07-13)

`docs/langsmith.md` reads three real traces: a cancel run whose tree ends at
the approval interrupt, the post-approval resume where the write node first
appears, and a policy answer with its verified citation. The README links it
with a teaser image; the console GIF waits for slice 8.

### 8.0 — Ticket registry (2026-07-13)

A separate SQLite registry now indexes ticket ids for CLI/API listing while
LangGraph checkpoints remain the source of truth for status. New CLI tickets
refuse reused registry ids or existing graph threads; approval resumes are unchanged.

### 8.1 — FastAPI wrapper (2026-07-13)

The localhost API now creates, lists, reads, and decides tickets through the
existing graph. Pydantic models expose validated state and the approval payload,
including the gate reason; stubbed HTTP tests make no Shopify or model calls.

### Hardening — order binding (2026-07-13)

Order references are allowlisted (`#`+digits), the returned order must match
the reference exactly, and the approval screen shows requested vs. found.
A hostile reference fails softly with zero Shopify calls.
