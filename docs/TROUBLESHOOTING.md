# Troubleshooting

Problems we hit and how we fixed them. Newest first. Format: symptom → cause → fix.

---

## PowerShell curl request reached FastAPI with invalid JSON (2026-07-13)

**Symptom:** A JSON-looking `curl.exe -d` command returned 422 with
`json_invalid` and "Expecting property name enclosed in double quotes."

**Cause:** PowerShell's native-command argument handling removed the embedded
JSON quotes before curl sent the body.

**Fix:** Build the body with `ConvertTo-Json`, pipe it to `curl.exe`, and use
`--data-binary '@-'` to read the exact JSON from standard input.

## Temporary SQLite database stayed locked on Windows (2026-07-13)

**Symptom:** Registry tests passed their assertions but cleanup failed with
`PermissionError: [WinError 32]` for `tickets.sqlite`.

**Cause:** A `sqlite3.Connection` context manager commits or rolls back but
does not close the connection.

**Fix:** Wrap each short-lived registry connection with `contextlib.closing`
so Windows can release and delete the database file immediately.

## Refund came back as 0.0 USD (2026-07-13)

**Symptom:** `refundCreate` succeeded but refunded 0.0 USD, and the order
stayed PAID. Earlier attempts found no refundable transaction at all, and
`maximumRefundableV2` was null even on an order with a real SALE transaction.

**Cause:** Seed orders created with `financialStatus: PAID` but no
`transactions` have no payment to reverse — Shopify can only mark their items
refunded. Hand-picking transactions by `maximumRefundableV2` also breaks
because manual-gateway transactions report it as null.

**Fix:** Ask Shopify instead of guessing: `order.suggestedRefund` returns the
exact transactions to reverse; feed them to `refundCreate`. The seed script
now attaches a captured SALE transaction to new orders so they refund like
really-paid orders.

## refundCreate rejected: @idempotent directive required (2026-07-13)

**Symptom:** `refundCreate` failed with "The @idempotent directive is
required for this mutation but was not provided."

**Cause:** The 2026-04 Admin API requires an idempotency key on refund
mutations.

**Fix:** Add `@idempotent(key: $idempotencyKey)` to the mutation field. We
derive the key from the order id, which doubles as protection against a
resumed graph node refunding the same order twice.

## OpenRouter rejected every call with 401 (2026-07-12)

**Symptom:** `UnauthorizedResponseError: Missing Authentication header`, even
though `OPENROUTER_API_KEY` was set and loaded.

**Cause:** The key was a bare 64-character hex string — a provisioning-style
key, not an inference key. OpenRouter returns its generic "missing header"
message for keys it doesn't recognize.

**Fix:** Create an API key at openrouter.ai → Settings → Keys and use that.
Inference keys start with `sk-or-v1-`.

## Old seed order passed the refund rule (2026-07-12)

**Symptom:** A 40-day-old seeded order appeared new.

**Cause:** Shopify `createdAt` was today; the seeded date was in `processedAt`.

**Fix:** Normalize `processedAt` as the order date used by the policy gate.

## Order query blocked after scopes were deployed (2026-07-12)

**Symptom:** Auth worked, but `orders` returned a protected customer data error.

**Cause:** The app had no distribution method, so the installed grant was stale.

**Fix:** Select **Custom distribution**, uninstall the app, then reinstall it.
Order queries now work. The token lists `write_orders`, not `read_orders`.

**Seed status:** 50/50 orders exist. Reruns create only missing segments;
use `--plan` to preview.

## Shopify auth: from `app_not_installed` to granted scopes (2026-07-12)

### How scopes flow

Scopes live in four places. They only move forward at specific moments:

```
shopify.app.*.toml            what you WANT
      |  shopify app deploy
      v
released app version          what the app DECLARES
      |  Install app -> consent screen -> approve
      v
store's grant to the app      what the store GRANTED (frozen at consent)
      |  POST /admin/oauth/access_token
      v
token `scope` field           what API calls CAN DO
```

Editing the TOML does nothing until you deploy. Deploying does nothing for a
store that already installed — the grant froze at consent time. The token
mirrors the grant, not the config. On `ACCESS_DENIED`, ask: which stage did
the scopes stop at?

### `app_not_installed` from the token endpoint

Valid credentials are not enough — client credentials only works for installed
apps. Fix: Dev Dashboard → app → Installs → Install app.

Same error while installed = the `.env` credentials belong to a different app
or an old secret. Compare Client IDs.

### Token works, but `ACCESS_DENIED` on `orders`

The token carried zero scopes — we log the token's `scope` field as
`ShopifyClient.granted_scopes`. Two causes stacked:

1. The version live at install time declared no scopes, so the store granted none.
2. `use_legacy_install_flow = true` — legacy flow never grants config scopes
   for a UI-less app.

Fix: set `use_legacy_install_flow = false` in the TOML,
`shopify app deploy --allow-updates`, reinstall the app.

### CLI: "No app with client ID ... found"

Our hand-written TOML had a client ID copied from a screenshot, one chunk
duplicated. Every CLI command failed, some with misleading errors.

Fix: `shopify app config link` — the CLI writes the TOML with the real ID.
Rule: never copy IDs from screenshots; use a machine source (copy button,
CLI, API response).

### Browser lands on "Example Domain" after install

Harmless. Shopify redirects to the app's `application_url` after install; ours
was the `example.com` placeholder. UI-less apps should use
`https://shopify.dev/apps/default-app-home`.

### Tools that cracked it

- `ShopifyClient.granted_scopes` — turns "auth is broken" into "the store
  granted nothing".
- `shopify app config link` — the CLI's own list of your apps; if it can't see
  the app there, no deploy will either.
