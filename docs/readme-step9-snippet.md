
<!-- wbms:step-09 -->
## Payments: the callback (Step 9)

`POST /api/payments/callback/<CALLBACK_SECRET>` receives the gateway result
(Daraja-style STK callback).

| Case | Result |
|---|---|
| wrong secret | 403, nothing changes |
| success, amount matches | transaction `success` with receipt and `paid_at`, session started |
| failure (for example ResultCode 1032) | transaction `failed` |
| duplicate, unknown reference, malformed body | 200, nothing changes |
| amount differs from the transaction | 200, stays `pending`, no access, warning logged |

The gateway always receives `{"ResultCode": 0, "ResultDesc": "Accepted"}` once the
secret is right. Until Step 11 the session start is a no-op placeholder.
Update the status table: Step 9 is done, Step 10 is next.
