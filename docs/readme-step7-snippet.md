
## Payment gateway (Step 7)

Payments go through the `PaymentGateway` interface in `src/wbms/gateways/payments/`.
With `PAYMENT_GATEWAY=mock` (the default) a fake gateway is used: a phone number ending in
`0` fails, ending in `9` stays pending, anything else succeeds. See
`docs/step-07-payment-gateway.md`.

| Step | Status |
|------|--------|
| 1-3 Foundation | Done |
| 4 Packages repository | Done |
| 5 Package service and admin API | Done |
| 6 Captive portal page | Done |
| 7 Payment interface and mock gateway | Done |
| 8 Starting a payment (`POST /api/payments`) | Next |
