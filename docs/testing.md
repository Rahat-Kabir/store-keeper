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
