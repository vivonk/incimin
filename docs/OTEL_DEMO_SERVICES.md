# OTel Demo Minimal Mode Services

**Version:** 3.0.0
**Command used:** `docker compose -f docker/otel-demo/compose.yaml config --services`

## Verified Service List
The minimal mode (which in version 3.0.0 is the base `compose.yaml`, with Kafka and other heavy services moved to `compose.full.yaml`) runs the following 20 services:

1. ad
2. astronomy-db
3. cart
4. checkout
5. currency
6. email
7. flagd
8. flagd-ui
9. frontend
10. frontend-proxy
11. image-provider
12. load-generator
13. otel-collector
14. payment
15. product-catalog
16. quote
17. recommendation
18. shipping
19. telemetry-docs
20. valkey-cart

## Services dropped in minimal mode
Full mode (`compose.yaml` + `compose.full.yaml`) adds the following 3 services:
1. accounting
2. fraud-detection
3. kafka

## Golden Path Services Confirmation
The three services required for the Phase 5 golden path are PRESENT in minimal mode.
Their exact OTel `service.name` values are:
- `payment` (Container: payment)
- `checkout` (Container: checkout)
- `frontend` (Container: frontend, plus `frontend-web` for browser telemetry)

