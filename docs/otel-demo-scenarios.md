# OpenTelemetry Demo: Agent Triage Scenarios

The OpenTelemetry Demo (Astronomy Shop) has a complex microservice graph. The `frontend` calls multiple downstream services. The `checkout` service is the central orchestrator, depending heavily on `cart`, `currency`, `shipping`, `payment`, `email`, and `kafka` queues.

Here are 8 realistic scenarios designed to test the Agent's ability to combine **topology blast-radius mapping** with **system events (PRs/Deployments)**.

---

## Scenario 1: The Cascading Payment Timeout
**The Event:** A bad PR is merged into `payment` service that introduces a 5-second sleep in the gRPC handler.
**The Deployment:** `payment` is deployed.
**The Alert:** High Latency Alert on `frontend` (P99 > 5s).
**Agent Reasoning Path:**
1. Agent checks `frontend` events -> No recent deployments.
2. Agent checks `frontend` topology -> Sees it depends on `checkout`.
3. Agent checks `checkout` topology -> Sees it depends on `payment`.
4. Agent checks events for `payment` -> Finds the recent deployment event.
5. **Conclusion:** A deployment to the `payment` service is backing up the `checkout` flow, causing the `frontend` to timeout.

## Scenario 2: Redis Connection Leak in Cart
**The Event:** A deployment happens on the `cart` service introducing a Redis connection pool leak.
**The Deployment:** `cart` is deployed.
**The Alert:** Error Rate Spike on `checkout` (Failed to place order).
**Agent Reasoning Path:**
1. Agent checks `checkout` events -> No deployments.
2. Agent pulls topology for `checkout` -> Sees it depends on `cart`.
3. Agent pulls topology for `cart` -> Sees it depends on `valkey/redis`.
4. Agent checks `cart` events -> Sees recent deployment.
5. **Conclusion:** `cart` deployment broke the state layer, bubbling errors up to `checkout`.

## Scenario 3: Bad Shipping Quote Logic
**The Event:** A PR is merged into the `quote` service (PHP) that accidentally returns negative values for heavy items.
**The Deployment:** `quote` is deployed.
**The Alert:** Anomalous Data Alert on `shipping` service (Negative shipping costs).
**Agent Reasoning Path:**
1. Agent sees alert on `shipping`. 
2. Agent checks `shipping` events -> No changes.
3. Agent checks `shipping` topology -> Sees it relies on `quote` service to calculate prices.
4. Agent checks `quote` events -> Sees a recent PR merge and deployment.
5. **Conclusion:** The `quote` service deployment introduced a logic bug affecting the upstream `shipping` service.

## Scenario 4: Kafka Queue Backup (Asynchronous Failure)
**The Event:** A config change PR is merged into `fraud-detection` that limits its Kafka consumer concurrency to 1.
**The Deployment:** `fraud-detection` is deployed.
**The Alert:** Kafka Topic Lag Alert on `orders` topic.
**Agent Reasoning Path:**
1. Agent checks who publishes/subscribes to `orders` topic using topology.
2. Sees `checkout` publishes, and `fraud-detection` and `accounting` subscribe.
3. Agent checks events for `fraud-detection` and `accounting`.
4. Finds recent PR merged into `fraud-detection`.
5. **Conclusion:** `fraud-detection` is processing orders too slowly due to a recent change, causing queue lag.

## Scenario 5: Missing Feature Flag for Recommendations
**The Event:** A PR in `flagd` (feature flag service) deletes the flag configuration for the new recommendation algorithm.
**The Deployment:** `flagd` is updated.
**The Alert:** 500 Error Spike on `recommendation` service.
**Agent Reasoning Path:**
1. Agent gets alert on `recommendation`.
2. Checks `recommendation` events -> No code changes.
3. Checks `recommendation` topology -> Sees it depends on `product-catalog` and `flagd`.
4. Checks `flagd` events -> Sees a recent configuration push/PR.
5. **Conclusion:** The `flagd` update removed a required flag, breaking the `recommendation` service.

## Scenario 6: The "Noisy Neighbor" Ad Service
**The Event:** A deployment in `ad` service introduces an aggressive retry loop when calling `flagd`, effectively DDOSing it.
**The Deployment:** `ad` service is deployed.
**The Alert:** High CPU/Latency on `flagd`.
**Agent Reasoning Path:**
1. Agent gets alert on `flagd`.
2. Checks `flagd` events -> No recent deployments.
3. Checks topology for `flagd` -> Sees it is called by `ad`, `checkout`, `fraud-detection`, `recommendation`.
4. Agent checks system events for ALL downstream callers.
5. Finds a deployment just occurred on `ad`.
6. **Conclusion:** The `ad` service deployment introduced a noisy-neighbor bug that is overloading the shared `flagd` service.

## Scenario 7: Currency Conversion Precision Bug
**The Event:** A PR in `currency` (C++) changes a float to an integer, causing rounding errors in conversions.
**The Deployment:** `currency` is deployed.
**The Alert:** Business Metric Drop: "Total Revenue Drop (Currency Mismatch)" detected by the `checkout` service.
**Agent Reasoning Path:**
1. Agent sees revenue mismatch alert originating from `checkout`.
2. Checks `checkout` topology -> Sees it calls `currency`.
3. Checks `currency` events -> Finds recent PR merge.
4. **Conclusion:** The PR in the `currency` service corrupted the exchange rate math used by `checkout`.

## Scenario 8: Frontend Memory Leak
**The Event:** A UI library update PR is merged into `frontend` (Next.js).
**The Deployment:** `frontend` is deployed.
**The Alert:** OOMKilled (Out of Memory) on `frontend` pods.
**Agent Reasoning Path:**
1. Agent gets OOM alert on `frontend`.
2. Checks `frontend` events -> Finds recent deployment.
3. Checks `frontend` topology -> Determines no upstream services are the cause; the blast radius is self-contained.
4. **Conclusion:** Direct rollback required on the `frontend` service due to a library memory leak.
