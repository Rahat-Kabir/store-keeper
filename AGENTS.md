# storekeeper — Agent Instructions

## Overview

Early v1 prototype of a CLI-first AI support agent for a Shopify store. The
current build connects to a live development store and provides test orders.
Dangerous store actions are enforced by code and human approval.

## Docs

- `README.md` — public face of the repo. Update in the same slice when the
  pipeline shape, quickstart commands, or user-visible behavior changes.
- `docs/VISION.md` — the why. Every feature must serve it; question anything that doesn't.
- `docs/PROGRESS.md` — feature log: roadmap checklist + ~3 lines per shipped
  feature. Features only, no repo chores. Update after changes; read before
  claiming what's built or what's next.
- `docs/TROUBLESHOOTING.md` — problem log: symptom → cause → fix, newest first.
  Add an entry whenever a non-trivial problem gets solved. Use simple words and
  as few of them as the fix needs — plain sentences, no drama.
- `docs/tech_spec.md` — as-built spec. Update when architecture, schema, or contracts change.
- `docs/langsmith.md` — trace walkthrough with screenshots in `docs/images/`.
  Update when graph node names or the pipeline shape change.
- `docs/testing.md` — verification workflow. Update when it changes.
- Doc style: clarity first — add words when understanding needs them;
  otherwise fewest words that carry the meaning.

## Architecture

- Python 3.11+ project managed with uv and a `src/` layout.
- Shopify GraphQL Admin API through one shared `ShopifyClient`.
- `shopify/operations.py` converts Shopify responses into domain facts.
- OAuth client credentials with in-memory token caching and one retry on 401.
- Live dev-store data; no Shopify mocks in the main workflow.
- Shared business contracts in `domain.py`; deterministic rules in `policy/`.
- Ticket classifier in `classify.py`: LangChain structured output on
  `ChatOpenRouter`; the model slug comes from the `OPENROUTER_MODEL` env var.
- LangGraph pipeline in `graph/`: a ticket-level graph wraps a per-task
  subgraph (lookup → gate → approval interrupt → execute). All routing is
  plain Python; checkpoints persist in `var/checkpoints.sqlite` with
  `thread_id` = ticket id.
- Ticket registry in `var/tickets.sqlite` indexes ticket ids, text, and creation
  time for CLI/API listing. Status is always derived from LangGraph checkpoints.
- FastAPI operator API in `api/` exposes ticket create, list, detail, and
  approval decisions under `/api/`. It invokes the graph and registry only;
  it never calls Shopify or an LLM directly.
- Policy corpus in `policies/` (markdown, one topic per file).
  `policy_docs.find_policy_context()` is the retrieval seam: action intents
  read mapped whole docs, while policy questions retrieve top-three heading
  chunks from local Chroma. Policy text feeds the answering/drafting LLMs only,
  never the gate.

### Key Decisions

- **One Shopify client wrapper** — keeps token handling and API errors in one place.
- **Custom app distribution** — fits a self-hosted app used on a store the owner controls.
- **Resumable seed script** — reruns create only missing segments, avoiding duplicates.
- **Old seed orders stay 40–59 days old** — tests the 30-day rule without requiring
  Shopify's `read_all_orders` scope.
- **Policy gate has no framework dependencies** — business rules cannot be changed
  by ticket text, prompts, or model behavior.
- **Refund age uses Shopify `processedAt`** — imported orders keep their real order
  date there, while `createdAt` is when Shopify created the record.
- **Order binding is strict** — a reference must be '#'+digits (allowlist, not
  escaping) and the returned order's name must match it exactly; ticket text
  can never steer an action onto a different order. The approval payload shows
  the customer-written reference next to the resolved order.
- **Classifier picks intent only** — `requested_action` is derived in code from a
  fixed intent→action mapping, so the model cannot emit an inconsistent pair.
- **Classifier returns a task list even in v1** — multi-request tickets split into
  one task per request; the v2 planner plugs into this socket without a rewrite.
- **Approval is a graph position, not a prompt** — `await_approval` calls
  `interrupt()` on the only edge that leads to `execute_action`; the human
  decision routes via `Command`, and SQLite checkpoints let it survive restarts.
- **Refunds follow `order.suggestedRefund`** — Shopify computes which payment
  transactions to reverse instead of us guessing; transactionless (imported)
  orders get their items marked refunded.
- **`refundCreate` uses an order-derived idempotency key** — required by the
  2026-04 API, and it makes a re-executed graph node unable to refund twice.
- **Address changes never guess missing fields** — the classifier extracts only
  what the customer supplied; incomplete addresses escalate. Complete requests
  still pass the gate and approval interrupt before `orderUpdate`, and omitted
  recipient identity fields are preserved from the current order.
- **Policy answers cite verified sources** — the answering LLM must name the
  documents it used, and code drops any citation that wasn't actually provided.
- **Policy RAG stays behind one seam** — `find_policy_context()` owns local
  Chroma retrieval, while action-denial citations keep deterministic whole-doc
  lookup. The graph, prompts, citation verification, and gate do not depend on
  the vector store.
- **Gate numbers are official policy (30 days / $100)** — locked 2026-07-13;
  `policies/` docs and `gate.py` constants must always tell the same story.

## Key Files

| File | ~Lines | Purpose |
|---|---:|---|
| `src/storekeeper/config.py` | 65 | Loads and validates Shopify + classifier settings. |
| `src/storekeeper/shopify/client.py` | 100 | Handles auth and GraphQL requests. |
| `src/storekeeper/shopify/operations.py` | 130 | Order lookup with strict binding and address normalization. |
| `src/storekeeper/shopify/writes.py` | 295 | Approved cancel, refund, and address-update writes. |
| `src/storekeeper/domain.py` | 80 | Shared business data contracts. |
| `src/storekeeper/classify.py` | 140 | LLM task classification and address extraction. |
| `src/storekeeper/policy/gate.py` | 100 | Pure action-eligibility rules. |
| `src/storekeeper/policy_docs.py` | 295 | Policy chunking, Chroma index/search, and retrieval seam. |
| `src/storekeeper/tickets.py` | 165 | Ticket registry, id generation, lookup, and checkpoint-derived status. |
| `src/storekeeper/api/app.py` | 195 | FastAPI lifecycle, graph seam, and ticket endpoints. |
| `src/storekeeper/api/schemas.py` | 95 | Validated operator API request and response models. |
| `src/storekeeper/graph/state.py` | 30 | Ticket and task state schemas. |
| `src/storekeeper/graph/nodes.py` | 345 | Graph nodes, routes, approval interrupt, policy answers. |
| `src/storekeeper/graph/build.py` | 110 | Assembles ticket graph + task subgraph. |
| `scripts/smoke_shopify.py` | 30 | Verifies the live store connection. |
| `scripts/seed_store.py` | 300 | Creates and resumes the 50-order test dataset. |
| `scripts/check_order_policy.py` | 50 | Runs the gate against one live order. |
| `scripts/classify_ticket.py` | 30 | Classifies one ticket from the CLI. |
| `scripts/index_policies.py` | 15 | Rebuilds the local Chroma policy index. |
| `scripts/search_policy.py` | 30 | Shows top policy chunks and cosine distances. |
| `scripts/run_ticket.py` | 95 | Runs or resumes one ticket through the graph. |
| `tests/test_policy_gate.py` | 125 | Policy rule and boundary tests. |
| `tests/test_shopify_operations.py` | 115 | Order lookup and normalization tests. |
| `tests/test_classify.py` | 190 | Classifier schema, mapping, and conversion tests. |
| `tests/test_shopify_writes.py` | 315 | Cancel, refund, and address-write tests. |
| `tests/test_policy_docs.py` | 150 | Policy chunking, routing, and gate-consistency tests. |
| `tests/test_graph.py` | 460 | Graph routing, interrupt, resume, and answering tests. |
| `tests/test_tickets.py` | 135 | Ticket registry, unique-id, lookup, and status tests. |
| `tests/test_api.py` | 220 | Stubbed HTTP workflow and API error-contract tests. |

## Commands

```powershell
uv sync
uv run python scripts/smoke_shopify.py
uv run python scripts/check_order_policy.py '#1001' cancel_order
uv run python scripts/classify_ticket.py "Please cancel order #1036."
uv run python scripts/classify_ticket.py "Change order #1036 to 20 Lake Road, Dhaka, Dhaka 1205, Bangladesh."
uv run python scripts/index_policies.py
uv run python scripts/search_policy.py "How long is your warranty?"
uv run python scripts/run_ticket.py TICKET-1 "Please cancel order #1001."
uv run python scripts/run_ticket.py TICKET-2 "Change order #1002 to 20 Lake Road, Dhaka, Dhaka 1205, Bangladesh."
uv run python scripts/run_ticket.py TICKET-1 --approve
uv run uvicorn storekeeper.api.app:app --host 127.0.0.1 --port 8000
uv run python scripts/seed_store.py --plan
uv run python scripts/seed_store.py
uv run python -m unittest discover -s tests -v
```

## Conventions

- All Shopify API calls go through `ShopifyClient`.
- Ticket-pipeline Shopify writes live only in `shopify/writes.py` and run only
  from the execute node, after the gate and the human approval. (The seed
  script is a separate, operator-run write path for test data.)
- The policy gate must not import LLM, LangChain, LangGraph, retrieval, or Shopify code.
- Rebuild the policy index after editing anything in `policies/`.
- Run the seed script with `--plan` before live creation.
- Keep `AGENTS.md` current in the same implementation slice when architecture,
  commands, key files, or project conventions change.

## Definition of Done

- Changed Python files compile.
- Relevant CLI checks pass.
- Shopify changes are verified against the live development store.
- Documentation matches the as-built behavior.

## Engineering Principles

- Simplicity first. No overengineering, no "flexibility" that wasn't asked for.
- Readability over simplicity: when the two conflict, the readable version wins.
- Surgical changes: touch only what's necessary; don't reformat adjacent code.
- Goal-driven: define verifiable success criteria, then make them pass.
- Fail fast: don't swallow exceptions; only catch with a specific recovery plan.
- Clean up orphans: removing code means removing its unused imports, tests,
  and dependencies too.

## Code Style

### Naming

IMPORTANT: follow these naming rules strictly. Clarity is the top priority.

- Be as clear and specific with variable and method names as possible.
- Optimize for clarity over concision. A developer with zero context on the
  codebase should immediately understand what a variable or method does just
  from reading its name.
- Use longer names when it improves clarity. Do NOT use single-character
  variable names.
- Follow the language's casing convention: `snake_case` in Python,
  `camelCase` in JavaScript/TypeScript.
- Example: use `original_question_last_answered_date` (Python) or
  `originalQuestionLastAnsweredDate` (JS/TS) instead of `original_answered`.
- When passing props or arguments to functions, keep the same names as the
  original variable. Do not shorten or abbreviate parameter names. If you have
  `currentCardData`, pass it as `currentCardData`, not `card` or `cardData`.

### Code Clarity

- Clear is better than clever. Do not write functionality in fewer lines if it
  makes the code harder to understand.
- Write more lines of code if additional lines improve readability and
  comprehension.
- Make things so clear that someone with zero context would completely
  understand the variable names, method names, what things do, and why they exist.
- When a variable or method name alone cannot fully explain something, add a
  comment explaining what is happening and why — in code you write or change.

## Do NOT

- Do not add features, refactor code, or make "improvements" beyond what was asked.
- Do not add docstrings, comments, or type annotations to code you did not change.
- Do not introduce new tech — library, framework, model, or provider —
  without asking first.

## Git Workflow

- Branch naming: `feature/description` or `fix/description`.
- Commit messages: Conventional Commits (`feat:`, `fix:`, `docs:`, …),
  imperative mood, concise, explain the "why" not the "what".
- Do not force-push to main.

## Self-Update

When you make changes to this project that affect the information in this
file, update this file to reflect those changes. Specifically:

- **New files**: if the Key Files table exists, add notable new source files
  to it with their purpose and approximate line count.
- **Deleted files**: remove entries for files that no longer exist.
- **Architecture changes**: update the Architecture section if you introduce
  new patterns, frameworks, or significant structural changes.
- **Build changes**: update the Commands section if the build process changes.
- **New conventions**: if the user establishes a new coding convention during
  a session, add it to the appropriate conventions section.
- **Line count drift**: if a file's line count changes significantly
  (>50 lines), update the approximate count in the Key Files table.
- **Empty slots**: when something a slot describes first comes into existence
  (a verification workflow, a new `docs/` file), fill that slot and delete its
  guidance comment.

Do NOT update this file for minor edits, bug fixes, or changes that don't
affect the documented architecture or conventions.
