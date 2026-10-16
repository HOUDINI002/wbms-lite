
<!-- wbms:step-07 -->
## Payments: gateway interface and mock (Step 7)

`src/wbms/gateways/payments/` holds the `PaymentGateway` protocol, the
deterministic `MockPaymentGateway` (phone ending in 0 fails, ending in 9 stays
pending, anything else succeeds) and `get_gateway(settings)`.
Set `PAYMENT_GATEWAY=mock` (default) for development.

<!-- wbms:step-08 -->
## Payments: starting a payment (Step 8)

`POST /api/payments` with `{"phone": "0712345671", "package_id": 1, "mac": "AA:BB:CC:DD:EE:FF"}`

| Status | Meaning |
|---|---|
| 202 | `{"transaction_id": 12, "status": "pending"}` |
| 400 | invalid JSON, missing or invalid fields (`fields` lists them) |
| 429 | more than 5 requests per minute from one IP (see `Retry-After`) |
| 502 | payment provider failed; the transaction is marked `failed` |

A repeated request for the same phone and package within 2 minutes returns the
existing pending transaction instead of charging twice.

Existing databases need one migration (new `transactions.mac_address` column):

```powershell
python scripts\add_mac_to_transactions.py
```

| Step | Status |
|---|---|
| 1-6 Foundation, catalog, portal | done |
| 7 Payment interface and mock | done |
| 8 Start payment | done |
| 9 Payment callback | next |
