# Staging WooCommerce Testing

This runbook is for the private staging WooCommerce connection only. Do not use
production WooCommerce credentials for this workflow.

## Credentials

Store WooCommerce credentials only in `backend/.env` or deployment secret
configuration. Never commit credentials, print them in logs, place them in
docs, or expose them to the frontend. The React frontend must call only the
Pongo OS backend.

REST connection and deliberate live-writeback test variables:

```bash
WOOCOMMERCE_BASE_URL=https://staging-host.example/
WOOCOMMERCE_CONSUMER_KEY=ck_replace_me
WOOCOMMERCE_CONSUMER_SECRET=cs_replace_me
WOOCOMMERCE_ENVIRONMENT=staging
WOOCOMMERCE_ALLOWED_HOST=staging-host.example
WOOCOMMERCE_READ_ENABLED=true
WOOCOMMERCE_READ_ONLY=false
WOOCOMMERCE_WRITEBACK_ENABLED=true
WOOCOMMERCE_WRITEBACK_DRY_RUN=false
WOOCOMMERCE_STAGING_LIVE_TEST_MODE=true
WOOCOMMERCE_ALLOW_STOCK_WRITE=true
WOOCOMMERCE_ALLOW_ORDER_STATUS_WRITE=true
WOOCOMMERCE_ALLOW_PRODUCT_METADATA_WRITE=false
WOOCOMMERCE_ALLOW_CUSTOMER_WRITE=false
WOOCOMMERCE_ALLOW_COUPON_WRITE=false
WOOCOMMERCE_ALLOW_REFUND_WRITE=false
WOOCOMMERCE_ALLOW_DELETE=false
```

For safe non-live testing, set `WOOCOMMERCE_WRITEBACK_DRY_RUN=true` or
`WOOCOMMERCE_STAGING_LIVE_TEST_MODE=false`.

The inbound webhook does not require live writeback. Keep writeback disabled
and read-only enabled unless a separate, deliberate writeback test is in scope.

## Order Webhook Configuration

Safe defaults in `backend/.env.example` are:

```bash
WOOCOMMERCE_WEBHOOK_ENABLED=false
WOOCOMMERCE_WEBHOOK_SECRET=
WOOCOMMERCE_WEBHOOK_MAX_BODY_BYTES=1048576
```

To test the receiver intentionally on staging:

```bash
WOOCOMMERCE_WEBHOOK_ENABLED=true
WOOCOMMERCE_WEBHOOK_SECRET=<distinct random value of at least 32 bytes>
WOOCOMMERCE_WEBHOOK_MAX_BODY_BYTES=1048576
WOOCOMMERCE_ALLOWED_HOST=staging-host.example
WOOCOMMERCE_READ_ONLY=true
WOOCOMMERCE_WRITEBACK_ENABLED=false
WOOCOMMERCE_WRITEBACK_DRY_RUN=true
WOOCOMMERCE_STAGING_LIVE_TEST_MODE=false
```

Use the same webhook secret in WooCommerce and the backend deployment secret
store. Do not reuse it in frontend code, a URL query string, screenshots, test
fixtures, logs, or committed documentation.

WooCommerce must be able to reach the Pongo backend over public HTTPS. A local
URL such as `http://127.0.0.1:8000` is not reachable from staging. Use an
approved deployed backend or approved secure tunnel and set the delivery URL to:

```text
https://<public-backend-host>/api/integrations/woocommerce/webhooks/orders
```

In WooCommerce, go to **WooCommerce > Settings > Advanced > Webhooks** and add:

- Name: `Pongo OS Order Created`
- Status: `Active`
- Topic: `Order created`
- Delivery URL: the public HTTPS endpoint above
- Secret: the exact value in `WOOCOMMERCE_WEBHOOK_SECRET`
- API version: current WP REST API integration version

Phase 1 imports only `order.created`. Do not configure `order.updated` or
`order.deleted` as operational Pongo webhooks yet. If an authenticated different
topic reaches the endpoint, Pongo records it as ignored and returns success
without changing an order.

The first activation sends an unsigned body in the exact form
`webhook_id=<positive integer>`. Pongo returns `status = ready` and performs no
database mutation. All JSON deliveries require `Content-Type: application/json`
and a valid `X-WC-Webhook-Signature` generated as base64 HMAC-SHA256 over the
exact raw body. Pongo also validates the topic/resource/event relationship,
webhook/delivery IDs, request size, and `X-WC-Webhook-Source` host.

See the official [WooCommerce webhook documentation](https://developer.woocommerce.com/docs/apis/rest-api/v2/webhooks)
and [current webhook implementation](https://woocommerce.github.io/code-reference/files/woocommerce-includes-class-wc-webhook.html)
for the delivery headers and signature algorithm.

## Live Writeback Guard

Live staging send is blocked unless every guard passes:

- environment is `staging`
- live staging test mode is true
- writeback is enabled
- dry-run is false
- read-only is false
- base URL host exactly matches `WOOCOMMERCE_ALLOWED_HOST`
- method is `PUT` or `PATCH`
- operation type is allowlisted
- path is allowlisted for that operation
- payload contains only allowlisted fields

Allowed operation types:

- `update_product_stock`
- `update_variation_stock`
- `update_order_status`

Allowed payload fields:

- Stock: `stock_quantity`, `stock_status`, `manage_stock`
- Order status: `status`

Always blocked:

- DELETE
- POST writes
- arbitrary endpoints
- customer writes
- coupon writes
- refund writes
- product metadata writes
- production WooCommerce writeback

## Manual QA

1. Start the backend from `backend/` after applying migrations through
   `20260710_0019`.
2. Start the frontend from `frontend/`.
3. Open Settings and confirm WooCommerce shows `Environment: staging`, webhook
   enabled/configured state, and no secret value.
4. Run Check Connection for the REST fallback.
5. Create/activate the WooCommerce `Order created` webhook and confirm the setup
   ping receives HTTP 200 with no order or webhook-event row created.
6. Place one fake staging order and confirm the delivery log receives HTTP 200.
7. Confirm one `woocommerce_webhook_deliveries` row has topic `order.created`, a
   processed status, a local order reference, and no raw payload/secret.
8. Confirm the order appears in Open Orders and the internal staff new-order
   notice appears once with a working View Open Orders action. Confirm the
   header Bell shows one unread item, opening its session history marks it read,
   and the history closes with Escape/Close.
9. Redeliver the same Woo delivery and confirm it returns `duplicate`, increments
   its attempt count, and does not duplicate the order, allocation, or notice.
10. Send a signed `order.updated` test only in isolated API testing and confirm it
    is audited as ignored without changing the order or showing a new-order
    notice.
11. Import a newer order snapshot through REST, then deliver an older signed
    `order.created` snapshot for the same order. Confirm the delivery is audited
    as ignored, the local order does not regress, and no notice appears.
12. Confirm a fresh frontend session calls the event feed with
    `initialize=true`, then polls every 2 seconds with `after_id=next_after_id`
    and drains all pages while `has_more=true`.
13. Confirm the 10-second quick sync still reconciles the open order. A nonzero
    `created_count` may produce one fallback notice, but repeating the same
    `sync_run_id` must not re-notify it.
14. Confirm a valid active order with enough local stock is auto-allocated,
    appears in both Open Orders and Pick Orders, leaves In Stock unchanged, and
    creates no stock movement during import.
15. Pick the test order and confirm local In Stock/Allocated are reduced by the
    pick, not by webhook import or fulfillment.
16. Complete the picked order from Open Orders and confirm stock is not reduced
    again.
17. Confirm Business Dashboard and Pongo Insights read the synced local data.
18. Only for a separate deliberate staging-writeback test, preview, queue,
    approve, and send an allowlisted stock/order-status writeback.
19. Confirm no REST keys, webhook secret, or raw customer webhook payload appear
    in browser dev tools, API responses, delivery ledger, or application logs.

Normal order sync, auto-allocation, picking, and completion are local Pongo OS
workflows. They must not send WooCommerce writes directly, even when staging
writeback is configured.

The internal new-order notice is local staff UI feedback. It is not a customer
email, SMS, browser push notification, or WooCommerce write.
