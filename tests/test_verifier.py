import time
import unittest

from src.agent.state import Synthesis
from src.agent.subagents.verifier import verify

NOW_NS = time.time_ns()


def make_evidence(id_, source, service, timestamp=None):
    return {"id": id_, "source": source, "service": service, "summary": "", "raw": {}, "timestamp": timestamp}


class TestVerifier(unittest.TestCase):
    def setUp(self):
        self.evidence = [
            make_evidence("topology-0", "topology", "paymentservice"),
            make_evidence("telemetry-err-0", "telemetry", "paymentservice", timestamp=NOW_NS),
        ]
        self.candidate_services = ["paymentservice"]

    def test_passes_when_fully_grounded_and_consistent(self):
        synthesis = Synthesis(
            root_cause_service="paymentservice",
            evidence_refs=["topology-0", "telemetry-err-0"],
            confidence="high",
        )
        result = verify(self.evidence, self.candidate_services, synthesis)
        self.assertTrue(result["passed"])
        self.assertEqual(result["failed_checks"], [])

    def test_fails_when_synthesis_missing(self):
        result = verify(self.evidence, self.candidate_services, None)
        self.assertFalse(result["passed"])
        self.assertEqual(result["failed_checks"], ["missing_synthesis"])

    def test_fails_when_no_evidence_refs(self):
        synthesis = Synthesis(root_cause_service="paymentservice", evidence_refs=[])
        result = verify(self.evidence, self.candidate_services, synthesis)
        self.assertFalse(result["passed"])
        self.assertIn("evidence_grounding", result["failed_checks"])

    def test_fails_when_evidence_ref_does_not_exist(self):
        synthesis = Synthesis(root_cause_service="paymentservice", evidence_refs=["telemetry-err-99"])
        result = verify(self.evidence, self.candidate_services, synthesis)
        self.assertFalse(result["passed"])
        self.assertIn("evidence_grounding", result["failed_checks"])

    def test_fails_when_evidence_ref_belongs_to_different_service(self):
        evidence = self.evidence + [make_evidence("telemetry-1", "telemetry", "cartservice", NOW_NS)]
        synthesis = Synthesis(root_cause_service="paymentservice", evidence_refs=["telemetry-1"])
        result = verify(evidence, self.candidate_services, synthesis)
        self.assertFalse(result["passed"])
        self.assertIn("evidence_grounding", result["failed_checks"])

    def test_fails_when_topology_disagrees(self):
        evidence = self.evidence + [make_evidence("telemetry-cart", "telemetry", "cartservice", NOW_NS)]
        synthesis = Synthesis(root_cause_service="cartservice", evidence_refs=["telemetry-cart"])
        result = verify(evidence, self.candidate_services, synthesis)
        self.assertFalse(result["passed"])
        self.assertIn("cross_modal_consistency", result["failed_checks"])

    def test_fails_when_telemetry_disagrees(self):
        synthesis = Synthesis(root_cause_service="paymentservice", evidence_refs=["topology-0"])
        result = verify([self.evidence[0]], self.candidate_services, synthesis)
        self.assertFalse(result["passed"])
        self.assertIn("cross_modal_consistency", result["failed_checks"])

    def test_fails_on_future_telemetry_timestamp(self):
        evidence = self.evidence[:2] + [
            make_evidence("telemetry-future", "telemetry", "paymentservice", NOW_NS + 10**12)
        ]
        synthesis = Synthesis(root_cause_service="paymentservice", evidence_refs=["telemetry-future"])
        result = verify(evidence, self.candidate_services, synthesis)
        self.assertFalse(result["passed"])
        self.assertIn("temporal_ordering", result["failed_checks"])

    def test_fails_on_stale_telemetry_timestamp(self):
        stale_ns = NOW_NS - (48 * 60 * 60 * 1_000_000_000)
        evidence = self.evidence[:2] + [make_evidence("telemetry-stale", "telemetry", "paymentservice", stale_ns)]
        synthesis = Synthesis(root_cause_service="paymentservice", evidence_refs=["telemetry-stale"])
        result = verify(evidence, self.candidate_services, synthesis)
        self.assertFalse(result["passed"])
        self.assertIn("temporal_ordering", result["failed_checks"])


if __name__ == "__main__":
    unittest.main()
