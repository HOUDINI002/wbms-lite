# Step 7: payment interface and mock gateway

Code lives in `src/wbms/gateways/payments/`.

| File | Purpose |
|------|---------|
| `base.py` | `PaymentGateway` Protocol, `GatewayReceipt`, `GatewayResult`, `GatewayStatus`, `GatewayError`, `GatewayConfigError` |
| `mock.py` | `MockPaymentGateway`, a deterministic fake that records every call |
| `factory.py` | `get_gateway(settings)` picks the gateway from `PAYMENT_GATEWAY` |

## The contract

```python
class PaymentGateway(Protocol):
    def initiate(self, phone: str, amount_kes: int, reference: str) -> GatewayReceipt: ...
    def query(self, checkout_id: str) -> GatewayResult: ...
```

* `initiate` asks the provider to prompt the customer. It returns a
  `GatewayReceipt(checkout_id, status)`. As with a real M-Pesa STK push the
  status is `PENDING`: the request was accepted, the money has not moved yet.
* The final outcome arrives later, by callback (Step 9) or by `query`
  (reconciliation, Step 10). `query` returns `GatewayResult(status, receipt_number)`.
* Any failure to reach or use the provider raises `GatewayError`.

## Mock behavior

The last digit of the phone number decides what `query` reports.

| Phone ends in | `query` returns |
|---------------|-----------------|
| `0` | `FAILED`, no receipt |
| `9` | `PENDING` forever (until you call `settle`) |
| anything else | `SUCCESS` with a receipt like `MOCKRCPT000001` |

Examples: `254712345670` fails, `254712345679` stays pending, `254712345671` succeeds.

Test helpers on `MockPaymentGateway`:

* `calls` and `calls_to("initiate")`: what the service sent.
* `fail_with = GatewayError("down")`: simulates an outage on both methods.
* `settle(checkout_id, GatewayStatus.SUCCESS)`: resolve a pending payment (used by reconciliation tests).

## Choosing the gateway

`.env` already has `PAYMENT_GATEWAY=mock`. `get_gateway(settings)` returns the mock.
`PAYMENT_GATEWAY=daraja` raises `GatewayConfigError` until the real adapter
`wbms/gateways/payments/daraja.py` (class `DarajaGateway(settings)`) is added in the
later Daraja step. An unknown name also raises `GatewayConfigError`.

## How the next steps use it

* Step 8 `PaymentService.start_payment` calls `gateway.initiate(phone, amount, str(tx.id))`
  and stores `receipt.checkout_id` as `gateway_ref`. A `GatewayError` marks the transaction failed.
* Step 9 callback and Step 10 `reconcile_pending` use `gateway.query`.
