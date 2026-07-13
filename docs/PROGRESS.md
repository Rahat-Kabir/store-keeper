# Progress

## Roadmap

- [x] 1. Scaffold + Shopify client wrapper + smoke test
- [x] 2. `scripts/seed_store.py` — 50 live orders across all edge cases
- [x] 3. Shared domain contracts + pure `policy_gate` + unit tests
- [x] 3b. Live Shopify order lookup + policy-check CLI
- [x] 4. `classify` module (structured output, task list) + CLI
- [x] 5. Graph wiring: task pipeline subgraph + ticket wrapper + approval interrupt + SQLite checkpointer + CLI
- [x] 5b. Real Shopify writes behind the approval: cancel + full refund (address changes escalate)
- [ ] 5c. Address extraction in the classifier + `orderUpdate` shipping-address write
- [x] 6. Policy markdown docs + loader + policy-question handling
- [ ] 6b. RAG behind the `find_policy_context` seam (Chroma + FastEmbed, chunk by heading)
- [ ] 7. Polish: LangSmith trace check, README + GIF
- [ ] Hardening backlog: seed script argparse (`--plan` typo = live run),
      reject reuse of completed ticket ids, trim unused Shopify scopes
      (`read_customers`, `read_products`)

(Reordered 2026-07-12: policy docs moved after graph wiring — they feed only
the reply drafter, which doesn't exist yet. Classifier moved up.)

## Session log

### 2026-07-12 — Slice 1: Shopify client wrapper

Built:

- Project scaffold: uv-managed (`uv sync`, committed `uv.lock`), src layout,
  `pyproject.toml`, `.env.example`, `.gitignore`.
- `src/storekeeper/config.py` — env loading + validation, normalizes bare store
  handle to full `*.myshopify.com` domain.
- `src/storekeeper/shopify/client.py` — client credentials auth: `get_token()`
  caches the ~24h token in memory, refreshes 60s early, retries once with a
  fresh token on 401; single `graphql()` entry point that raises loudly on HTTP
  and GraphQL-level errors.
- `scripts/smoke_shopify.py` — **passed** against storekeeper-demo.myshopify.com (USD).
- Live Order query now passes after selecting Custom distribution and reinstalling the app.
- Seed store contains 50/50 planned orders. Reruns safely create only missing segments.

Setup gotchas (full story + mental model: [TROUBLESHOOTING.md](TROUBLESHOOTING.md)):

- The app must be installed on the store: Dev Dashboard → app → Installs → Install app.
- An App URL of `example.com` dead-ends the browser after install; use
  `https://shopify.dev/apps/default-app-home` for UI-less apps.
- `app_not_installed` from the token endpoint can also mean the `.env`
  credentials belong to a different app than the one installed — re-copy
  Client ID + secret from the app's Settings.

Next: slice 3 — pure `policy_gate` function and unit tests.

### 2026-07-12 — Slice 3: policy gate

Built shared domain types and deterministic rules for cancellation, refunds,
high-value flags, and address changes. All 9 unit tests pass.

Next: slice 4 — policy corpus and retrieval.

### 2026-07-12 — Slice 3b: live order policy check

Added read-only order lookup, Shopify-to-domain normalization, and a CLI policy
check. Live checks pass for recent, fulfilled, old, and high-value orders.

Refund age uses `processedAt`; Shopify `createdAt` did not preserve seeded age.

Next: slice 4 — policy markdown docs and a simple loader.

### 2026-07-12 — Slice 4: ticket classifier

Built:

- Renamed `Task.order_id` → `Task.order_reference` — it holds the order name
  as the customer wrote it, not the Shopify GraphQL id.
- Added `langchain` + `langchain-openrouter`. The model slug lives in
  `OPENROUTER_MODEL` (.env, currently `openai/gpt-5.5`);
  `load_classifier_settings()` validates the OpenRouter variables.
- `src/storekeeper/classify.py` — a Pydantic schema validates the LLM output,
  then converts it to domain `Task`s. The model picks only the intent;
  `requested_action` is derived in code from a fixed mapping. Output is a task
  list even in v1 (the v2 planner's socket).
- `scripts/classify_ticket.py` — CLI proof. 8 offline unit tests run against a
  fake model; no network in the suite.
- LangSmith tracing on via env vars (`LANGSMITH_TRACING=true`).

Live checks passed (`openai/gpt-5.5`): cancel with an order ref, policy
question with no order, a two-request ticket split into two ordered tasks, and
a refund with a bare order number copied exactly as written.

Next: slice 5 — graph wiring.

### 2026-07-12 — README + license

- Wrote the public README: thesis pitch, Mermaid pipeline diagram, real CLI
  output as the demo, quickstart, docs links. No roadmap section by design;
  the demo section is where the v1 GIF lands later.
- Added the MIT `LICENSE`.
- `AGENTS.md` now lists `README.md` as a doc to update in the same slice when
  user-visible behavior changes.

Next: slice 5 — graph wiring.

### 2026-07-13 — Slice 5: graph wiring with approval interrupt

Built:

- Added `langgraph` + `langgraph-checkpoint-sqlite`.
- `graph/state.py` — `TicketState` (ticket level) and `TaskState` (per task).
  `task_results` uses an append reducer so the v2 planner can fan out tasks.
- `graph/nodes.py` — nodes wrap the existing tested functions; all routing is
  plain Python route functions. `await_approval` calls `interrupt()` and
  routes the human decision via `Command`. The execute node is a stub
  (records what would happen); real writes are slice 5b. Bare order
  references like "1040" are normalized to "#1040" before lookup. A missing
  order becomes a `failed` task result and a polite reply, not a crash.
- `graph/build.py` — the per-task pipeline is a compiled subgraph invoked by
  a thin ticket-level wrapper (v2 socket). Ticket graph compiles with the
  checkpointer; the subgraph inherits it.
- `scripts/run_ticket.py` — CLI: new ticket runs until the interrupt and
  prints the pending approval; `--approve` / `--reject` resumes from
  `var/checkpoints.sqlite` in a fresh process. `thread_id` = ticket id.
- Reply drafting is a live LLM call from structured task results.
- 8 offline graph tests (29 total); no network in the suite.

Live checks passed: cancel ticket paused at approval, then `--approve` in a
separate process executed the stub and drafted the reply; `--reject` produced
a declined reply; a two-request ticket escalated without touching approval.

v1 escalates: multi-request tickets, policy questions (until slice 6), and
tickets with no order reference.

Next: slice 5b — real Shopify writes behind the approval.

### 2026-07-13 — Slice 5b: real Shopify writes

Built:

- `shopify/writes.py` — `cancel_order` (async `orderCancel` job; refunds the
  original payment, restocks) and `issue_full_refund` (Shopify's
  `suggestedRefund` computes which payment transactions to reverse;
  `refundCreate` carries an order-derived `@idempotent` key, so a re-run can
  never refund twice).
- The execute node calls these for real; nothing simulated remains.
- Address-change tickets escalate at classification — the classifier doesn't
  extract the new address yet (slice 5c).
- Seed script now attaches a captured SALE transaction to new orders, so they
  refund like really-paid orders. Existing transactionless seed orders
  exercise the imported-order path (items marked refunded, no charge to
  reverse).
- 37 tests; the suite also proves a rejected approval sends zero write calls.

Live checks passed: `#1003` cancelled (cancelledAt set on the store), `#1004`
line-item refund on a transactionless order, `#1051` refunded 42.0 USD with
financial status REFUNDED — each through classify → gate → interrupt →
approve in a separate process.

Next: slice 6 — policy docs + loader + policy-question handling (or 5c).

### 2026-07-13 — Slice 6: policy corpus + question answering

Built:

- `policies/` — five short markdown store-policy docs; numbers match the gate
  (30-day refunds, $100 extra review), rules match system behavior
  (unfulfilled-only cancellations, hand-applied address changes).
- `policy_docs.py` — `find_policy_context(task)` is the retrieval seam: v1
  returns whole files (mapped by intent; policy questions get the whole
  corpus). The RAG slice (6b) replaces its internals only.
- `answer_policy_question` node — structured output (`PolicyAnswer`) answers
  only from the provided docs; citations are verified against the provided
  file names, so a hallucinated citation is dropped. First use of
  `TaskResult.policy_citations`.
- Routing: `policy_question` tickets are answered instead of escalated.
- Denied actions now cite policy: `record_policy_denial` attaches the
  relevant document names, and `draft_reply` receives the policy text.
- 44 tests. Gate numbers locked as real policy: 30 days / $100.

Live checks passed: a warranty question answered from `warranty.md` with the
citation printed; a 61-day-old refund denied with the reply quoting the
30-day window and citing `returns-and-refunds.md`; a two-question ticket
still escalates (v1 multi-request rule).

Next: slice 6b (RAG behind the seam) or 5c (address extraction).

### 2026-07-13 — Publish hardening (pre-Git)

Driven by an external code review (Codex). The real find: **order binding was
loose** — the customer-written reference went straight into a Shopify search
query and `orders[0]` was trusted without checking its name. Ticket text
could steer an action onto a different order than the ticket appeared to
request.

Fixed with three layers in `operations.py` / `nodes.py`:

- References are allowlisted (`#` + digits, or rejected) before touching a query.
- The returned order's name must exactly equal the normalized reference.
- The approval payload shows the customer-written reference next to the
  resolved order, so the human audits the binding.

A hostile reference now fails softly through the graph (outcome `failed`,
polite reply, zero Shopify calls — tests prove it).

Also: `.claude/` gitignored; tech_spec refreshed (stale escalation line, new
"what leaves the machine" section, async-cancel note); AGENTS wording fixes;
README live-write warning + accurate OpenRouter description; `.env.example`
explains what tracing exports. 48 tests pass.

Backlog recorded in the roadmap: seed argparse, completed-ticket-id reuse
guard, scope trim.

Next: `git init`, inspect staged files, secret-scan, first commit.
