# Incident: CheckoutService High Latency

## Description
Checkout latency is spiking, causing users to abandon carts.

## Root Cause
Can be caused by downstream payment service delays or database lock contentions.

## Remediation
1. Check paymentservice health.
2. Investigate Redis/Valkey cache latency.
3. Scale out checkoutservice pods.
