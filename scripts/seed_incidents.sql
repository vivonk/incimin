-- Idempotent seed for demo/dev: 4 successful agent triages + 1 failed run.
-- Mirrors the shapes written by src/api/runner.py and src/api/repository.py.
-- Safe to re-run: DELETEs by the fixed UUIDs, then re-INSERTs.

BEGIN;

DELETE FROM incidents WHERE id IN (
    '11111111-1111-1111-1111-111111111111',
    '22222222-2222-2222-2222-222222222222',
    '33333333-3333-3333-3333-333333333333',
    '44444444-4444-4444-4444-444444444444',
    '55555555-5555-5555-5555-555555555555'
);

-- =========================================================================
-- 1. paymentservice — external Stripe timeout, deploy-correlated (SUCCESS)
-- =========================================================================
INSERT INTO incidents (
    id, dedupe_key, fingerprint, alertname, service, severity, message,
    generator_url, receiver, status, current_step,
    fired_at, resolved_at, created_at, updated_at,
    labels, annotations, raw,
    root_cause_service, confidence, evidence_refs, final_answer, error
) VALUES (
    '11111111-1111-1111-1111-111111111111',
    'HighErrorRate|paymentservice',
    'fp-payment-a1b2c3',
    'HighErrorRate',
    'paymentservice',
    'critical',
    'paymentservice error rate 47% over 5m (threshold 5%)',
    'http://signoz.local/alerts/1001',
    'sre-oncall',
    'done', NULL,
    now() - interval '42 minutes',
    now() - interval '38 minutes',
    now() - interval '42 minutes',
    now() - interval '38 minutes',
    '{"alertname":"HighErrorRate","service":"paymentservice","severity":"critical","team":"payments"}'::jsonb,
    '{"summary":"paymentservice error rate spike","runbook_url":"https://runbooks.local/payment-timeout"}'::jsonb,
    '{"status":"firing","labels":{"alertname":"HighErrorRate","service":"paymentservice","severity":"critical"},"annotations":{"summary":"paymentservice error rate spike"}}'::jsonb,
    'paymentservice',
    'high',
    '["signoz.error_logs#42","changes.deploys#7","runbook:payment-timeout"]'::jsonb,
    'Root cause: paymentservice v2.4.1 deploy at 14:12 UTC introduced a 500ms Stripe API timeout regression. Error rate went 0.3%→47% within 4 minutes of the rollout. Recommendation: roll back to v2.4.0 via `kubectl rollout undo deployment/paymentservice`.',
    NULL
);

INSERT INTO agent_steps (incident_id, seq, parent_seq, kind, name, status, input, output, started_at, ended_at) VALUES
    ('11111111-1111-1111-1111-111111111111', 1, NULL, 'node', 'plan', 'ok', NULL,
     '{"candidate_services":["paymentservice","checkoutservice","frontend"],"hypotheses":[{"id":"h1","kind":"deploy_regression","service":"paymentservice","posterior":0.42,"status":"active"},{"id":"h2","kind":"upstream_dependency","service":"checkoutservice","posterior":0.31,"status":"active"}]}'::jsonb,
     now() - interval '42 minutes', now() - interval '42 minutes' + interval '1 second'),
    ('11111111-1111-1111-1111-111111111111', 2, 1, 'tool_call', 'topology_bfs', 'ok',
     '{"source":"paymentservice","depth":2}'::jsonb, NULL,
     now() - interval '42 minutes' + interval '1 second', now() - interval '42 minutes' + interval '2 seconds'),
    ('11111111-1111-1111-1111-111111111111', 3, 1, 'tool_result', 'signoz.error_logs', 'ok', NULL,
     '{"summary":"42 error logs matching upstream=stripe timeout=500ms in last 5m","evidence_count":42,"round_index":1}'::jsonb,
     now() - interval '42 minutes' + interval '2 seconds', now() - interval '42 minutes' + interval '4 seconds'),
    ('11111111-1111-1111-1111-111111111111', 4, 1, 'tool_result', 'changes.deploys', 'ok', NULL,
     '{"summary":"1 deploy on paymentservice at 14:12 UTC (v2.4.0 -> v2.4.1)","evidence_count":1,"round_index":1}'::jsonb,
     now() - interval '42 minutes' + interval '4 seconds', now() - interval '42 minutes' + interval '5 seconds'),
    ('11111111-1111-1111-1111-111111111111', 5, NULL, 'node', 'verifier', 'ok', NULL,
     '{"verification_result":{"grounded":true,"unsupported_claims":[]},"hypotheses":[{"id":"h1","kind":"deploy_regression","service":"paymentservice","posterior":0.94,"status":"confirmed"}]}'::jsonb,
     now() - interval '42 minutes' + interval '6 seconds', now() - interval '42 minutes' + interval '9 seconds'),
    ('11111111-1111-1111-1111-111111111111', 6, NULL, 'node', 'finalize', 'ok', NULL,
     '{"synthesis":{"root_cause_service":"paymentservice","confidence":"high","evidence_refs":["signoz.error_logs#42","changes.deploys#7","runbook:payment-timeout"]},"budget":{"max_rounds":10,"rounds_used":2,"exit_reason":"converged"}}'::jsonb,
     now() - interval '42 minutes' + interval '9 seconds', now() - interval '42 minutes' + interval '11 seconds');


-- =========================================================================
-- 2. cartservice — Redis memory leak (SUCCESS, remediation approved)
-- =========================================================================
INSERT INTO incidents (
    id, dedupe_key, fingerprint, alertname, service, severity, message,
    generator_url, receiver, status, current_step,
    fired_at, resolved_at, created_at, updated_at,
    labels, annotations, raw,
    root_cause_service, confidence, evidence_refs, final_answer, error
) VALUES (
    '22222222-2222-2222-2222-222222222222',
    'RedisMemoryPressure|cartservice',
    'fp-cart-d4e5f6',
    'RedisMemoryPressure',
    'cartservice',
    'warning',
    'cart redis working set 92% of maxmemory over 10m',
    'http://signoz.local/alerts/1002',
    'sre-oncall',
    'done', NULL,
    now() - interval '3 hours',
    now() - interval '2 hours 51 minutes',
    now() - interval '3 hours',
    now() - interval '2 hours 51 minutes',
    '{"alertname":"RedisMemoryPressure","service":"cartservice","severity":"warning","team":"checkout"}'::jsonb,
    '{"summary":"Redis approaching maxmemory","runbook_url":"https://runbooks.local/redis-leak"}'::jsonb,
    '{"status":"firing","labels":{"alertname":"RedisMemoryPressure","service":"cartservice","severity":"warning"}}'::jsonb,
    'cartservice',
    'high',
    '["signoz.error_logs#18","changes.deploys#3","runbook:redis-leak"]'::jsonb,
    'Root cause: cartservice v3.1.0 (deployed 2h58m ago) leaks Redis keys — session TTL removed by mistake, keys accumulate at ~1.2MB/min. Working set will hit maxmemory in ~14m. Recommendation: revert commit a7f9e2c which dropped the SETEX ttl in `session_store.go`; short-term, run `FLUSHDB` on stale sessions older than 1h.',
    NULL
);

INSERT INTO agent_steps (incident_id, seq, parent_seq, kind, name, status, input, output, started_at, ended_at) VALUES
    ('22222222-2222-2222-2222-222222222222', 1, NULL, 'node', 'plan', 'ok', NULL,
     '{"candidate_services":["cartservice","redis-cart","checkoutservice"],"hypotheses":[{"id":"h1","kind":"resource_exhaustion","service":"redis-cart","posterior":0.55,"status":"active"},{"id":"h2","kind":"deploy_regression","service":"cartservice","posterior":0.28,"status":"active"}]}'::jsonb,
     now() - interval '3 hours', now() - interval '3 hours' + interval '1 second'),
    ('22222222-2222-2222-2222-222222222222', 2, 1, 'tool_result', 'signoz.error_logs', 'ok', NULL,
     '{"summary":"18 warnings: OOM eviction imminent, key count growing linearly","evidence_count":18,"round_index":1}'::jsonb,
     now() - interval '3 hours' + interval '1 second', now() - interval '3 hours' + interval '3 seconds'),
    ('22222222-2222-2222-2222-222222222222', 3, 1, 'tool_result', 'changes.deploys', 'ok', NULL,
     '{"summary":"cartservice v3.1.0 deployed 2h58m ago; diff removed SETEX TTL from session_store.go","evidence_count":3,"round_index":1}'::jsonb,
     now() - interval '3 hours' + interval '3 seconds', now() - interval '3 hours' + interval '4 seconds'),
    ('22222222-2222-2222-2222-222222222222', 4, NULL, 'node', 'verifier', 'ok', NULL,
     '{"verification_result":{"grounded":true,"unsupported_claims":[]},"hypotheses":[{"id":"h2","kind":"deploy_regression","service":"cartservice","posterior":0.91,"status":"confirmed"}]}'::jsonb,
     now() - interval '3 hours' + interval '5 seconds', now() - interval '3 hours' + interval '7 seconds'),
    ('22222222-2222-2222-2222-222222222222', 5, NULL, 'gate', 'remediation', 'ok', NULL,
     '{"proposal":{"action":"kubectl rollout undo deployment/cartservice","risk":"low"}}'::jsonb,
     now() - interval '3 hours' + interval '7 seconds', now() - interval '3 hours' + interval '7 seconds'),
    ('22222222-2222-2222-2222-222222222222', 6, NULL, 'node', 'execute_remediation', 'ok', NULL,
     '{"execution_result":{"ok":true,"detail":"rollout undo submitted; new pods healthy"}}'::jsonb,
     now() - interval '3 hours' + interval '8 minutes', now() - interval '3 hours' + interval '9 minutes'),
    ('22222222-2222-2222-2222-222222222222', 7, NULL, 'node', 'finalize', 'ok', NULL,
     '{"synthesis":{"root_cause_service":"cartservice","confidence":"high","evidence_refs":["signoz.error_logs#18","changes.deploys#3","runbook:redis-leak"]},"budget":{"max_rounds":10,"rounds_used":2,"exit_reason":"converged"}}'::jsonb,
     now() - interval '3 hours' + interval '9 minutes', now() - interval '3 hours' + interval '9 minutes' + interval '1 second');

INSERT INTO approvals (id, incident_id, step_seq, kind, proposal, decision, decided_by, decided_at, note, execution_result, created_at) VALUES (
    'a2222222-2222-2222-2222-222222222222',
    '22222222-2222-2222-2222-222222222222',
    5, 'remediation',
    '{"action":"kubectl rollout undo deployment/cartservice","risk":"low","target":"cartservice"}'::jsonb,
    'executed', 'alice@incimin.io', now() - interval '2 hours 52 minutes',
    'Approved — safe rollback, no schema changes',
    '{"ok":true,"detail":"rollout undo submitted; new pods healthy"}'::jsonb,
    now() - interval '3 hours' + interval '7 seconds'
);


-- =========================================================================
-- 3. quoteservice — logic regression, deploy-correlated (SUCCESS)
-- =========================================================================
INSERT INTO incidents (
    id, dedupe_key, fingerprint, alertname, service, severity, message,
    generator_url, receiver, status, current_step,
    fired_at, resolved_at, created_at, updated_at,
    labels, annotations, raw,
    root_cause_service, confidence, evidence_refs, final_answer, error
) VALUES (
    '33333333-3333-3333-3333-333333333333',
    'ShippingQuoteFailures|quoteservice',
    'fp-quote-g7h8i9',
    'ShippingQuoteFailures',
    'quoteservice',
    'critical',
    'quoteservice 500s at 22% of requests over 5m',
    'http://signoz.local/alerts/1003',
    'sre-oncall',
    'done', NULL,
    now() - interval '1 day 4 hours',
    now() - interval '1 day 3 hours 55 minutes',
    now() - interval '1 day 4 hours',
    now() - interval '1 day 3 hours 55 minutes',
    '{"alertname":"ShippingQuoteFailures","service":"quoteservice","severity":"critical","team":"logistics"}'::jsonb,
    '{"summary":"quote 500s spiking","runbook_url":"https://runbooks.local/quote-logic"}'::jsonb,
    '{"status":"firing","labels":{"alertname":"ShippingQuoteFailures","service":"quoteservice","severity":"critical"}}'::jsonb,
    'quoteservice',
    'high',
    '["signoz.error_logs#31","changes.deploys#4","runbook:quote-logic"]'::jsonb,
    'Root cause: quoteservice commit f2c8b91 (deployed 6m before alert) introduced a NoneType branch in `compute_price()` when the destination country lacks a shipping-zone override. 22% of requests are for countries hit by this. Recommendation: revert f2c8b91 and add a fallback zone lookup; regression test on countries {IN, BR, ZA}.',
    NULL
);

INSERT INTO agent_steps (incident_id, seq, parent_seq, kind, name, status, input, output, started_at, ended_at) VALUES
    ('33333333-3333-3333-3333-333333333333', 1, NULL, 'node', 'plan', 'ok', NULL,
     '{"candidate_services":["quoteservice","shippingservice","currencyservice"],"hypotheses":[{"id":"h1","kind":"deploy_regression","service":"quoteservice","posterior":0.48,"status":"active"}]}'::jsonb,
     now() - interval '1 day 4 hours', now() - interval '1 day 4 hours' + interval '1 second'),
    ('33333333-3333-3333-3333-333333333333', 2, 1, 'tool_result', 'signoz.error_logs', 'ok', NULL,
     '{"summary":"31 error logs: NoneType in compute_price; destination_country in {IN,BR,ZA}","evidence_count":31,"round_index":1}'::jsonb,
     now() - interval '1 day 4 hours' + interval '1 second', now() - interval '1 day 4 hours' + interval '3 seconds'),
    ('33333333-3333-3333-3333-333333333333', 3, 1, 'tool_result', 'changes.deploys', 'ok', NULL,
     '{"summary":"quoteservice deploy f2c8b91 landed 6m before alert","evidence_count":4,"round_index":1}'::jsonb,
     now() - interval '1 day 4 hours' + interval '3 seconds', now() - interval '1 day 4 hours' + interval '4 seconds'),
    ('33333333-3333-3333-3333-333333333333', 4, NULL, 'node', 'verifier', 'ok', NULL,
     '{"verification_result":{"grounded":true,"unsupported_claims":[]},"hypotheses":[{"id":"h1","kind":"deploy_regression","service":"quoteservice","posterior":0.93,"status":"confirmed"}]}'::jsonb,
     now() - interval '1 day 4 hours' + interval '5 seconds', now() - interval '1 day 4 hours' + interval '7 seconds'),
    ('33333333-3333-3333-3333-333333333333', 5, NULL, 'node', 'finalize', 'ok', NULL,
     '{"synthesis":{"root_cause_service":"quoteservice","confidence":"high","evidence_refs":["signoz.error_logs#31","changes.deploys#4","runbook:quote-logic"]},"budget":{"max_rounds":10,"rounds_used":1,"exit_reason":"converged"}}'::jsonb,
     now() - interval '1 day 4 hours' + interval '7 seconds', now() - interval '1 day 4 hours' + interval '8 seconds');


-- =========================================================================
-- 4. checkoutservice — Kafka consumer lag, upstream broker (SUCCESS)
-- =========================================================================
INSERT INTO incidents (
    id, dedupe_key, fingerprint, alertname, service, severity, message,
    generator_url, receiver, status, current_step,
    fired_at, resolved_at, created_at, updated_at,
    labels, annotations, raw,
    root_cause_service, confidence, evidence_refs, final_answer, error
) VALUES (
    '44444444-4444-4444-4444-444444444444',
    'CheckoutQueueLag|checkoutservice',
    'fp-checkout-j0k1l2',
    'CheckoutQueueLag',
    'checkoutservice',
    'warning',
    'checkout order-events consumer lag 12,400 messages',
    'http://signoz.local/alerts/1004',
    'sre-oncall',
    'done', NULL,
    now() - interval '6 hours',
    now() - interval '5 hours 48 minutes',
    now() - interval '6 hours',
    now() - interval '5 hours 48 minutes',
    '{"alertname":"CheckoutQueueLag","service":"checkoutservice","severity":"warning","team":"checkout"}'::jsonb,
    '{"summary":"Kafka consumer lag","runbook_url":"https://runbooks.local/kafka-backup"}'::jsonb,
    '{"status":"firing","labels":{"alertname":"CheckoutQueueLag","service":"checkoutservice","severity":"warning"}}'::jsonb,
    'kafka',
    'medium',
    '["signoz.error_logs#9","changes.deploys#0","runbook:kafka-backup"]'::jsonb,
    'Root cause: kafka broker-2 rebalance triggered by disk pressure (94% used on /var/lib/kafka), producing consumer partition reassignments and a 12k-message lag on order-events. Not a checkoutservice regression — no deploy in the last 24h. Recommendation: expand broker-2 volume to 500Gi; long-term add a disk-usage alert at 80%.',
    NULL
);

INSERT INTO agent_steps (incident_id, seq, parent_seq, kind, name, status, input, output, started_at, ended_at) VALUES
    ('44444444-4444-4444-4444-444444444444', 1, NULL, 'node', 'plan', 'ok', NULL,
     '{"candidate_services":["checkoutservice","kafka","orderservice"],"hypotheses":[{"id":"h1","kind":"upstream_dependency","service":"kafka","posterior":0.36,"status":"active"},{"id":"h2","kind":"deploy_regression","service":"checkoutservice","posterior":0.22,"status":"active"}]}'::jsonb,
     now() - interval '6 hours', now() - interval '6 hours' + interval '1 second'),
    ('44444444-4444-4444-4444-444444444444', 2, 1, 'tool_result', 'signoz.error_logs', 'ok', NULL,
     '{"summary":"9 broker-2 warnings: ISR shrink, disk 94%, partition reassignment","evidence_count":9,"round_index":1}'::jsonb,
     now() - interval '6 hours' + interval '1 second', now() - interval '6 hours' + interval '3 seconds'),
    ('44444444-4444-4444-4444-444444444444', 3, 1, 'tool_result', 'changes.deploys', 'ok', NULL,
     '{"summary":"no checkoutservice deploys in last 24h","evidence_count":0,"round_index":1}'::jsonb,
     now() - interval '6 hours' + interval '3 seconds', now() - interval '6 hours' + interval '4 seconds'),
    ('44444444-4444-4444-4444-444444444444', 4, NULL, 'node', 'plan', 'ok', NULL,
     '{"hypotheses":[{"id":"h1","kind":"upstream_dependency","service":"kafka","posterior":0.71,"status":"active"}]}'::jsonb,
     now() - interval '6 hours' + interval '5 seconds', now() - interval '6 hours' + interval '5 seconds'),
    ('44444444-4444-4444-4444-444444444444', 5, 4, 'tool_result', 'signoz.error_logs', 'ok', NULL,
     '{"summary":"kafka broker-2 disk /var/lib/kafka at 94%","evidence_count":6,"round_index":2}'::jsonb,
     now() - interval '6 hours' + interval '6 seconds', now() - interval '6 hours' + interval '8 seconds'),
    ('44444444-4444-4444-4444-444444444444', 6, NULL, 'node', 'verifier', 'ok', NULL,
     '{"verification_result":{"grounded":true,"unsupported_claims":[]},"hypotheses":[{"id":"h1","kind":"upstream_dependency","service":"kafka","posterior":0.82,"status":"confirmed"}]}'::jsonb,
     now() - interval '6 hours' + interval '9 seconds', now() - interval '6 hours' + interval '11 seconds'),
    ('44444444-4444-4444-4444-444444444444', 7, NULL, 'node', 'finalize', 'ok', NULL,
     '{"synthesis":{"root_cause_service":"kafka","confidence":"medium","evidence_refs":["signoz.error_logs#9","changes.deploys#0","runbook:kafka-backup"]},"budget":{"max_rounds":10,"rounds_used":2,"exit_reason":"converged"}}'::jsonb,
     now() - interval '6 hours' + interval '11 seconds', now() - interval '6 hours' + interval '12 seconds');


-- =========================================================================
-- 5. recommendationservice — noisy neighbor, agent exhausted budget (FAILED)
-- =========================================================================
INSERT INTO incidents (
    id, dedupe_key, fingerprint, alertname, service, severity, message,
    generator_url, receiver, status, current_step,
    fired_at, resolved_at, created_at, updated_at,
    labels, annotations, raw,
    root_cause_service, confidence, evidence_refs, final_answer, error
) VALUES (
    '55555555-5555-5555-5555-555555555555',
    'HighLatencyP99|recommendationservice',
    'fp-recs-m3n4o5',
    'HighLatencyP99',
    'recommendationservice',
    'warning',
    'recommendationservice p99 latency 2.4s over 10m (threshold 500ms)',
    'http://signoz.local/alerts/1005',
    'sre-oncall',
    'failed', NULL,
    now() - interval '20 minutes',
    NULL,
    now() - interval '20 minutes',
    now() - interval '17 minutes',
    '{"alertname":"HighLatencyP99","service":"recommendationservice","severity":"warning","team":"discovery"}'::jsonb,
    '{"summary":"recs p99 latency degraded"}'::jsonb,
    '{"status":"firing","labels":{"alertname":"HighLatencyP99","service":"recommendationservice","severity":"warning"}}'::jsonb,
    NULL, NULL, NULL,
    'Investigation inconclusive: no deploys on recommendationservice or its direct upstreams in the last 24h; error logs show no obvious failure mode. Latency is elevated on 3 of 4 pods but node-level metrics were not available to this agent. Handing off — likely noisy neighbor on shared node, but cannot confirm without k8s node telemetry.',
    'BudgetExhausted: exit_reason=max_rounds after 10 rounds; hypothesis posteriors did not converge (top=0.51 noisy_neighbor)'
);

INSERT INTO agent_steps (incident_id, seq, parent_seq, kind, name, status, input, output, started_at, ended_at) VALUES
    ('55555555-5555-5555-5555-555555555555', 1, NULL, 'node', 'plan', 'ok', NULL,
     '{"candidate_services":["recommendationservice","productcatalogservice","frontend"],"hypotheses":[{"id":"h1","kind":"deploy_regression","service":"recommendationservice","posterior":0.31,"status":"active"},{"id":"h2","kind":"upstream_dependency","service":"productcatalogservice","posterior":0.28,"status":"active"}]}'::jsonb,
     now() - interval '20 minutes', now() - interval '20 minutes' + interval '1 second'),
    ('55555555-5555-5555-5555-555555555555', 2, 1, 'tool_result', 'signoz.error_logs', 'ok', NULL,
     '{"summary":"no error logs above WARN in last 15m","evidence_count":0,"round_index":1}'::jsonb,
     now() - interval '20 minutes' + interval '1 second', now() - interval '20 minutes' + interval '3 seconds'),
    ('55555555-5555-5555-5555-555555555555', 3, 1, 'tool_result', 'changes.deploys', 'ok', NULL,
     '{"summary":"no deploys on recommendationservice in last 24h","evidence_count":0,"round_index":1}'::jsonb,
     now() - interval '20 minutes' + interval '3 seconds', now() - interval '20 minutes' + interval '4 seconds'),
    ('55555555-5555-5555-5555-555555555555', 4, NULL, 'node', 'plan', 'ok', NULL,
     '{"hypotheses":[{"id":"h3","kind":"resource_exhaustion","service":"recommendationservice","posterior":0.44,"status":"active"},{"id":"h4","kind":"noisy_neighbor","service":"recommendationservice","posterior":0.39,"status":"active"}]}'::jsonb,
     now() - interval '20 minutes' + interval '5 seconds', now() - interval '20 minutes' + interval '6 seconds'),
    ('55555555-5555-5555-5555-555555555555', 5, 4, 'tool_result', 'signoz.error_logs', 'ok', NULL,
     '{"summary":"latency elevated on pods {recs-7d4, recs-7d5, recs-7d6}; recs-7d3 normal","evidence_count":3,"round_index":2}'::jsonb,
     now() - interval '20 minutes' + interval '6 seconds', now() - interval '20 minutes' + interval '9 seconds'),
    ('55555555-5555-5555-5555-555555555555', 6, NULL, 'node', 'verifier', 'skipped', NULL,
     '{"verification_result":{"grounded":false,"unsupported_claims":["noisy neighbor without node-level cpu/memory evidence"]}}'::jsonb,
     now() - interval '20 minutes' + interval '10 seconds', now() - interval '20 minutes' + interval '12 seconds'),
    ('55555555-5555-5555-5555-555555555555', 7, NULL, 'node', 'graceful_exit', 'failed', NULL,
     '{"budget":{"max_rounds":10,"rounds_used":10,"exit_reason":"max_rounds"},"hypotheses":[{"id":"h4","kind":"noisy_neighbor","service":"recommendationservice","posterior":0.51,"status":"active"}]}'::jsonb,
     now() - interval '17 minutes', now() - interval '17 minutes' + interval '1 second');

COMMIT;

\echo 'Seeded 5 incidents (4 done + 1 failed). Counts:'
SELECT status, COUNT(*) FROM incidents GROUP BY status ORDER BY status;
SELECT 'agent_steps' AS table, COUNT(*) FROM agent_steps
UNION ALL SELECT 'approvals', COUNT(*) FROM approvals;
