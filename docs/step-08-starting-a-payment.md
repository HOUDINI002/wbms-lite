# Step 8: starting a payment (slide 67)

Creates the pending transaction, calls the gateway, records the reference.

## Files

| File | Purpose |
|---|---|
| `src/wbms/repositories/customers.py` | `Customer`, `CustomerRepository.upsert / get_by_phone` |
| `src/wbms/repositories/transactions.py` | `Transaction`, `TransactionRepository`, `iso_utc`, `ensure_mac_column` |
| `src/wbms/services/payments.py` | `PaymentService.start_payment`, `normalize_phone`, `normalize_mac` |
| `src/wbms/web/rate_limit.py` | `RateLimiter` (sliding window, injectable clock) |
| `src/wbms/web/api_payments.py` | `POST /api/payments` blueprint (`bp`) |
| `scripts/add_mac_to_transactions.py` | one-off migration for an existing database |
| `tests/unit/test_payments_service.py` and 3 more | 78 tests |

## How `start_payment` works

1. Normalize phone (`2547XXXXXXXX`) and MAC (`AA:BB:CC:DD:EE:FF`); look up the package. Unknown and inactive packages give the same error.
2. **DB transaction 1:** upsert customer, return an existing pending transaction if the same customer asked for the same package in the last 120 s (repeated request), otherwise insert a `pending` row.
3. Call `gateway.initiate(phone, amount, reference=str(transaction.id))` **outside** any DB transaction.
4. **DB transaction 2:** store `checkout_id` in `gateway_ref`; if the gateway raised, mark the row `failed` and re-raise (the API maps this to 502).

## Decisions worth knowing

- **MAC column.** The deck's `transactions` table has no MAC, but Step 9 needs it to start the session. Step 8 adds `transactions.mac_address`.
- **Repeated request** = same customer + package while a pending transaction is under 120 s old. It returns that transaction and does not charge twice. After a failure, retrying is allowed straight away.
- **Free packages (0 KES) are rejected** for payment: a mobile-money prompt for 0 makes no sense.
- **Clock** = a function returning an aware UTC `datetime`. A naive datetime raises `ValueError`.
- **Rate limit** is per process and keyed on `request.remote_addr`. Behind a proxy use werkzeug `ProxyFix`.
- Logs show only the last 3 digits of a phone number.

## Error bodies

`{"error": "validation_error", "message": "...", "fields": {"phone": "..."}}` (400),
`{"error": "rate_limited", ...}` + `Retry-After` (429), `{"error": "gateway_error", ...}` (502).
If your Step 5 routes use a different JSON error shape, change `_error()` in `api_payments.py` to match.
