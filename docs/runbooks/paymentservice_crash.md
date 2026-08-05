# Incident: PaymentService Crash

## Description
The PaymentService is crashing unexpectedly, often leading to a spike in Checkout latency.

## Root Cause
Often caused by an unhandled exception or memory leak in the payment processing logic.

## Remediation
1. Restart the paymentservice deployment.
2. Check logs for unhandled exceptions.
3. If necessary, rollback to the previous stable version.
