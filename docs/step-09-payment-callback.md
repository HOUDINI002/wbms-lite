# Step 9: the payment callback (slide 68)

Applies the gateway's result to the transaction, atomically and exactly once.

## Flow of `PaymentService.apply_callback(payload)`

One database transaction around everything:

1. Parse `Body.stkCallback` (`CheckoutRequestID`, `ResultCode`, `ResultDesc`, `CallbackMetadata.Item`). Missing or wrong-typed fields give `INVALID`; nothing changes.
2. Find the transaction by `gateway_ref`. Unknown gives `IGNORED`.
3. Not `pending` any more gives `DUPLICATE`; nothing changes (also for a failure after a success, or a success after a failure).
4. `ResultCode != 0`: `pending -> failed`, reason logged, `FAILED`.
5. `ResultCode == 0`: receipt present and `Amount` equal to the transaction amount, else `INVALID` or `AMOUNT_MISMATCH` (stays pending, no access). Then `pending -> success` with `receipt` and `paid_at` in **one** UPDATE (your schema requires `paid_at` exactly when status is success), then `start_session(transaction, mac)`.

`UPDATE ... WHERE status = 'pending'` is the exactly-once guard: two racing callbacks cannot both win.

## Route

`POST /api/payments/callback/<secret>`

- Wrong or empty configured secret: **403**, nothing changes (constant-time `hmac.compare_digest`).
- Right secret: always **200** `{"ResultCode": 0, "ResultDesc": "Accepted"}`, whatever the outcome (unknown, duplicate, malformed, internal error). The outcome is logged. The deck says "always 200" and also, in Step 86/89, "wrong secret returns 403"; both are honoured: 403 is for callers who are not the gateway.
- If something raises (for example the session start), the database change is rolled back, the transaction stays `pending`, and the gateway still gets 200. Step 10's reconcile job will ask the gateway about it.

## Things to know

- **SessionService does not exist yet** (it is Step 11). Until then `NoopSessionStarter` records the payment and logs `session_start_skipped`; it grants no access. In Step 11, store the real service in `app.extensions["wbms_session_starter"]`.
- **Amount mismatch** leaves the transaction `pending` (not failed): money may have moved, so a person should look at it. Log line: `callback_amount_mismatch`.
- **Failure reason** is only logged (there is no column for it).
- **Secret** comes from `CALLBACK_SECRET` in `.env` (Step 1 settings). Never log it; the callback URL contains it, so keep access logs private.
