"""Layer 1 gates, v2.

Covers the two behaviours that changed from `tests/test_verifier.py`: cross-source consistency
counts distinct sources instead of hardcoding topology-and-telemetry, and temporal ordering is
measured against the alert rather than wall-clock.
"""
import time
import unittest

from src.agent.kernel.state import Hypothesis
from src.agent.kernel.verifier import MAX_LOOKBACK_NS, POST_ALERT_GRACE_NS, verify

FIRED_AT_NS = time.time_ns() - 5 * 60 * 1_000_000_000  # alert fired 5 minutes ago


def ev(id_, source, service, timestamp=None):
    return {
        "id": id_,
        "source": source,
        "service": service,
        "summary": "",
        "raw": {},
        "timestamp": timestamp,
    }


def hyp(service="paymentservice", supporting=(), refuting=(), posterior=1.0, status="open"):
    return Hypothesis(
        id="h1",
        kind="dependency_failure",
        statement=f"{service} is the cause",
        subject_service=service,
        origin="topology",
        prior=posterior,
        posterior=posterior,
        status=status,
        supporting_refs=list(supporting),
        refuting_refs=list(refuting),
    )


class TestVerifierV2(unittest.TestCase):
    def setUp(self):
        self.evidence = [
            ev("topology/0", "topology", "paymentservice"),
            ev("signoz.error_logs/0", "telemetry", "paymentservice", FIRED_AT_NS),
        ]
        self.refs = ["topology/0", "signoz.error_logs/0"]

    def _verify(self, hypothesis, evidence=None, **kw):
        kw.setdefault("alert_fired_at_ns", FIRED_AT_NS)
        kw.setdefault("stop_reason", "converged")
        return verify([hypothesis], evidence or self.evidence, **kw)

    def test_passes_when_grounded_across_two_sources(self):
        result = self._verify(hyp(supporting=self.refs))
        self.assertTrue(result["passed"], result["detail"])
        self.assertEqual(result["failed_checks"], [])

    def test_fails_with_no_surviving_hypothesis(self):
        result = verify([], self.evidence)
        self.assertFalse(result["passed"])
        self.assertEqual(result["failed_checks"], ["no_surviving_hypothesis"])

    def test_fails_when_nothing_is_cited(self):
        result = self._verify(hyp(supporting=[]))
        self.assertIn("evidence_grounding", result["failed_checks"])

    def test_fails_on_dangling_evidence_ref(self):
        result = self._verify(hyp(supporting=["signoz.error_logs/99"]))
        self.assertIn("evidence_grounding", result["failed_checks"])

    def test_fails_when_cited_evidence_is_about_another_service(self):
        evidence = self.evidence + [ev("t/1", "telemetry", "cartservice", FIRED_AT_NS)]
        result = self._verify(hyp(supporting=["t/1"]), evidence)
        self.assertIn("evidence_grounding", result["failed_checks"])

    # --- cross-source consistency: the generalized gate --------------------------------

    def test_fails_on_a_single_source(self):
        result = self._verify(hyp(supporting=["signoz.error_logs/0"]))
        self.assertIn("cross_source_consistency", result["failed_checks"])

    def test_any_two_distinct_sources_satisfy_the_gate(self):
        """v1 hardcoded topology AND telemetry. A team adding a third source must be able to
        satisfy this without touching the kernel."""
        evidence = [
            ev("changes.deploys/0", "changes", "paymentservice", FIRED_AT_NS),
            ev("team.flags/0", "flags", "paymentservice", FIRED_AT_NS),
        ]
        result = self._verify(
            hyp(supporting=["changes.deploys/0", "team.flags/0"]), evidence
        )
        self.assertNotIn("cross_source_consistency", result["failed_checks"])

    def test_min_distinct_sources_is_configurable(self):
        result = self._verify(hyp(supporting=self.refs), min_distinct_sources=3)
        self.assertIn("cross_source_consistency", result["failed_checks"])

    # --- temporal ordering: now relative to the alert, not the clock -------------------

    def test_fails_when_evidence_postdates_the_alert_beyond_grace(self):
        late = FIRED_AT_NS + POST_ALERT_GRACE_NS + 10**11
        evidence = self.evidence + [ev("t/late", "telemetry", "paymentservice", late)]
        result = self._verify(hyp(supporting=["topology/0", "t/late"]), evidence)
        self.assertIn("temporal_ordering", result["failed_checks"])

    def test_allows_symptoms_arriving_shortly_after_the_alert(self):
        soon = FIRED_AT_NS + 60 * 1_000_000_000
        evidence = self.evidence + [ev("t/soon", "telemetry", "paymentservice", soon)]
        result = self._verify(hyp(supporting=["topology/0", "t/soon"]), evidence)
        self.assertNotIn("temporal_ordering", result["failed_checks"])

    def test_fails_on_evidence_far_older_than_the_alert(self):
        stale = FIRED_AT_NS - MAX_LOOKBACK_NS - 10**11
        evidence = self.evidence + [ev("t/stale", "telemetry", "paymentservice", stale)]
        result = self._verify(hyp(supporting=["topology/0", "t/stale"]), evidence)
        self.assertIn("temporal_ordering", result["failed_checks"])

    def test_atemporal_evidence_is_exempt(self):
        result = self._verify(hyp(supporting=self.refs))
        self.assertNotIn("temporal_ordering", result["failed_checks"])

    # --- new gates ---------------------------------------------------------------------

    def test_fails_when_the_winner_still_carries_contradicting_evidence(self):
        result = self._verify(hyp(supporting=self.refs, refuting=["signoz.error_logs/9"]))
        self.assertIn("refutation_integrity", result["failed_checks"])

    def test_budget_exhaustion_is_recorded_but_does_not_fail_the_run(self):
        result = self._verify(hyp(supporting=self.refs), stop_reason="budget_exhausted")
        self.assertTrue(result["passed"])
        self.assertIn("budget_exhausted", result["detail"])


if __name__ == "__main__":
    unittest.main()
