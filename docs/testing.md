# Testing

```powershell
uv run python -m unittest discover -s tests -v
uv run python -m compileall -q src scripts tests
uv run python scripts/smoke_shopify.py
uv run python scripts/seed_store.py --plan
uv run python scripts/check_order_policy.py '#1001' cancel_order
uv run python scripts/classify_ticket.py "Please cancel order #1036. I ordered it by mistake."
uv run python scripts/classify_ticket.py "Change order #1036 to 20 Lake Road, Dhaka, Dhaka 1205, Bangladesh."
uv run python scripts/index_policies.py
uv run python scripts/search_policy.py "How long is your warranty?"
uv run python scripts/run_ticket.py TICKET-1 "Please cancel order #1001."
uv run python scripts/run_ticket.py TICKET-1 --approve
uv run python scripts/run_ticket.py TICKET-2 "How long is your warranty?"
uv run python scripts/run_ticket.py TICKET-3 "Change order #1036 to 20 Lake Road, Dhaka, Dhaka 1205, Bangladesh."
uv run uvicorn storekeeper.api.app:app --host 127.0.0.1 --port 8000
```

Unit tests are local and make no Shopify or model calls. The remaining commands
are live checks: `classify_ticket.py` and `run_ticket.py` make paid OpenRouter
model calls, and **approving a `run_ticket.py` action executes a real write on
the store** (cancel, refund, or address update). Running `--approve` in
a separate invocation from the ticket run verifies that the approval interrupt
survives a process restart (state lives in `var/checkpoints.sqlite`).

`index_policies.py` and `search_policy.py` are local and need no API key. The
first run downloads Chroma's MiniLM ONNX model once. Rebuild the index after
editing any file in `policies/`; cosine distances printed by the search CLI are
lower for more similar chunks.

With the API running, use `curl.exe` in PowerShell to verify the HTTP wrapper:

```powershell
$ticketId = "TICKET-API-CURL-1"
$ticketBody = @{ticket_id = $ticketId; ticket_text = "Please cancel order #1003."} | ConvertTo-Json -Compress
$ticketBody | curl.exe -s -X POST localhost:8000/api/tickets -H "Content-Type: application/json" --data-binary '@-'
curl.exe -s localhost:8000/api/tickets
curl.exe -s "localhost:8000/api/tickets/$ticketId"
$decisionBody = @{decision = "reject"} | ConvertTo-Json -Compress
$decisionBody | curl.exe -s -X POST "localhost:8000/api/tickets/$ticketId/decision" -H "Content-Type: application/json" --data-binary '@-'
```

Creating and resolving tickets makes paid OpenRouter calls. An `approve`
decision can execute a real Shopify write; use `reject` when verifying the API
without changing the development store.

For the browser flow, keep FastAPI running on port 8000 and Vite on port 5173.
In a second PowerShell terminal, run:

```powershell
cd frontend
npm run build
npm run lint
npm run dev
```

Open `http://127.0.0.1:5173`, create the policy question `How long is your
warranty?`, and verify that the new ticket appears first in the list with an
Answered badge. Its detail view must show a reply draft and the verified
`warranty.md` citation. The Copy draft button must copy the displayed reply.
This live flow makes paid OpenRouter calls but performs no Shopify write.

To verify the approval inbox, create a cancellation for a known unfulfilled
development-store order. Confirm the card shows the customer reference beside
the resolved order, amount, gate rule and reason, and any flags. Reject one
eligible ticket and verify the order stays unchanged. Approve another only when
a real development-store write is intended; verify Shopify records the write
and the final draft appears immediately. A refund for an order older than 30
days must resolve as Denied by policy with a citation and never enter the inbox.

For an address-change ticket, confirm the card shows the current and proposed
addresses side by side. Rejecting it must preserve the original Shopify address.

To verify single-process serving, stop Vite after the frontend checks, build the
console, and run only FastAPI:

```powershell
cd frontend
npm run build
cd ..
uv run uvicorn storekeeper.api.app:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000` and repeat the create, detail, and safe reject
flow. Confirm `curl.exe -s -I http://127.0.0.1:8000/` returns an HTML response
and `curl.exe -s http://127.0.0.1:8000/api/tickets` still returns JSON. Removing
or renaming `frontend/dist` is not required for normal verification; the unit
suite covers API-only startup when the build is absent.
