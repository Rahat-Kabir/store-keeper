# Testing

```powershell
uv run python -m unittest discover -s tests -v
uv run python -m compileall -q src scripts tests
uv run python scripts/smoke_shopify.py
uv run python scripts/seed_store.py --plan
uv run python scripts/check_order_policy.py '#1001' cancel_order
uv run python scripts/classify_ticket.py "Please cancel order #1036. I ordered it by mistake."
uv run python scripts/index_policies.py
uv run python scripts/search_policy.py "How long is your warranty?"
uv run python scripts/run_ticket.py TICKET-1 "Please cancel order #1001."
uv run python scripts/run_ticket.py TICKET-1 --approve
uv run python scripts/run_ticket.py TICKET-2 "How long is your warranty?"
```

Unit tests are local and make no Shopify or model calls. The remaining commands
are live checks: `classify_ticket.py` and `run_ticket.py` make paid OpenRouter
model calls, and **approving a `run_ticket.py` action executes a real write on
the store** (cancel or refund), consuming a seed order. Running `--approve` in
a separate invocation from the ticket run verifies that the approval interrupt
survives a process restart (state lives in `var/checkpoints.sqlite`).

`index_policies.py` and `search_policy.py` are local and need no API key. The
first run downloads Chroma's MiniLM ONNX model once. Rebuild the index after
editing any file in `policies/`; cosine distances printed by the search CLI are
lower for more similar chunks.
