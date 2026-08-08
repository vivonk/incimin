"""The kernel loop end to end, with stubbed probes and no model in the loop.

Runs under `INCIMIN_DETERMINISTIC=1`, which is the same mode the golden path uses. If these
tests ever need an API key, the determinism escape hatch has stopped working.
"""
import asyncio
import time
import unittest
from typing import ClassVar
from unittest import mock

from src.agent.kernel import graph as kernel
from src.agent.kernel.state import Evidence
from src.agent.probes import registry as reg
from src.agent.probes.base import ProbeManifest, ProbeRequest, ProbeResult
from src.agent.subagents.topology import TopologyResult

FIRED_AT_NS = time.time_ns() - 2 * 60 * 1_000_000_000


def topology_evidence(service: str, idx: int = 0) -> Evidence:
    return {
        "id": f"topology-{idx}",
        "source": "topology",
        "service": service,
        "summary": f"alertsvc -> {service}",
        "raw": {},
        "timestamp": None,
    }


def stub_probe(probe_id, source, discriminates, service, *, rows=1, status="ok"):
    class _P:
        manifest: ClassVar[ProbeManifest] = ProbeManifest(
            id=probe_id, source=source, discriminates=list(discriminates), cost_tier="cheap"
        )

        async def run(self, req: ProbeRequest) -> ProbeResult:
            if status != "ok":
                return ProbeResult(status=status, summary="stub produced nothing")
            return ProbeResult(
                evidence=[
                    {
                        "id": f"{probe_id}/{i}",
                        "source": source,
                        "service": service,
                        "summary": f"stub {source} row {i}",
                        "raw": {},
                        "timestamp": FIRED_AT_NS,
                    }
                    for i in range(rows)
                ],
                summary=f"stub returned {rows} row(s)",
            )

    return _P()


class KernelGraphTest(unittest.TestCase):
    """Base fixture: deterministic mode, stub topology, stub probe roster."""

    candidates = ["paymentservice", "cartservice"]
    topology_service = "paymentservice"

    def setUp(self):
        self.env = mock.patch.dict("os.environ", {"INCIMIN_DETERMINISTIC": "1"})
        self.env.start()
        reg.reset()
        self.register_probes()
        self.topology = mock.patch.object(
            kernel,
            "run_topology_subagent",
            return_value=TopologyResult(
                candidate_services=self.candidates,
                evidence=[topology_evidence(self.topology_service)],
                summary="stub traversal",
            ),
        )
        self.topology.start()
        self.app = kernel.build_graph().compile()

    def tearDown(self):
        self.topology.stop()
        self.env.stop()
        reg.reset()

    def register_probes(self):
        reg.register(
            stub_probe("signoz.error_logs", "telemetry", ["dependency_failure"], "paymentservice")
        )

    def run_graph(self, **alert):
        payload = {
            "alertname": "HighLatency",
            "service": "checkoutservice",
            "severity": "critical",
            "fired_at_ns": FIRED_AT_NS,
            **alert,
        }
        return asyncio.run(self.app.ainvoke({"alert": payload, "messages": []}))


class TestGoldenPath(KernelGraphTest):
    def test_converges_and_reports_a_root_cause(self):
        out = self.run_graph()
        self.assertTrue(out["verification_result"]["passed"], out["verification_result"]["detail"])
        self.assertEqual(out["synthesis"].root_cause_service, "paymentservice")
        self.assertEqual(out["synthesis"].confidence, "high")

    def test_converges_in_a_single_round(self):
        out = self.run_graph()
        self.assertEqual(out["budget"].rounds_used, 1)
        self.assertEqual(out["budget"].exit_reason, "converged")

    def test_report_cites_two_distinct_sources(self):
        out = self.run_graph()
        by_id = {e["id"]: e for e in out["evidence"]}
        sources = {by_id[r]["source"] for r in out["synthesis"].evidence_refs}
        self.assertEqual(sources, {"topology", "telemetry"})

    def test_report_lists_what_was_ruled_out(self):
        """Google SRE makes 'options considered and rejected' a hard requirement; a single-pass
        agent structurally cannot produce it."""
        text = out_text(self.run_graph())
        self.assertIn("Ruled out:", text)
        self.assertIn("cartservice", text)

    def test_report_names_the_probes_it_ran(self):
        self.assertIn("Probes run: signoz.error_logs", out_text(self.run_graph()))

    def test_no_probe_runs_twice(self):
        keys = [r["dedup_key"] for r in self.run_graph()["probe_log"]]
        self.assertEqual(len(keys), len(set(keys)))

    def test_repeated_runs_are_identical(self):
        results = {
            (
                o["synthesis"].root_cause_service,
                o["synthesis"].confidence,
                tuple(o["synthesis"].evidence_refs),
                o["budget"].rounds_used,
            )
            for o in (self.run_graph() for _ in range(3))
        }
        self.assertEqual(len(results), 1)


class TestNoEvidence(KernelGraphTest):
    """Every probe comes back empty: the run must fail closed, not invent a cause."""

    def register_probes(self):
        reg.register(
            stub_probe("signoz.error_logs", "telemetry", ["dependency_failure"], "x", status="empty")
        )

    def test_fails_verification_on_a_single_source(self):
        out = self.run_graph()
        self.assertFalse(out["verification_result"]["passed"])
        self.assertIn("cross_source_consistency", out["verification_result"]["failed_checks"])

    def test_says_it_does_not_know(self):
        self.assertIn("Insufficient evidence", out_text(self.run_graph()))

    def test_still_surfaces_its_best_unconfirmed_guess(self):
        """Failing closed should not mean failing silent — the on-call still needs a lead."""
        self.assertIn("Best unconfirmed explanation", out_text(self.run_graph()))

    def test_running_out_of_probes_is_not_reported_as_running_out_of_budget(self):
        """Dedup exhausts the useful probes long before the round budget is spent. Reporting
        that as `budget_exhausted` tells the on-call to grant more time when the real answer
        is that there is nothing left to look at — and it would mis-segment the eval harness.
        """
        out = self.run_graph()
        budget = out["budget"]
        self.assertEqual(budget.exit_reason, "no_discriminating_probe")
        self.assertLess(budget.rounds_used, budget.max_rounds)


class TestProbeFailure(KernelGraphTest):
    """A dead evidence source degrades a run; it does not end one."""

    def register_probes(self):
        class Exploding:
            manifest: ClassVar[ProbeManifest] = ProbeManifest(
                id="broken.probe",
                source="telemetry",
                discriminates=["dependency_failure"],
                cost_tier="cheap",
            )

            async def run(self, req):
                raise RuntimeError("data plane is on fire")

        reg.register(Exploding())
        reg.register(
            stub_probe("changes.deploys", "changes", ["deploy_regression"], "paymentservice")
        )

    def test_run_completes_despite_a_raising_probe(self):
        out = self.run_graph()
        statuses = {r["probe_id"]: r["status"] for r in out["probe_log"]}
        self.assertEqual(statuses["broken.probe"], "error")
        self.assertTrue(out["verification_result"]["passed"], out["verification_result"]["detail"])

    def test_surviving_probe_still_contributes_evidence(self):
        out = self.run_graph()
        self.assertIn("changes", {e["source"] for e in out["evidence"]})


class TestNoCandidates(KernelGraphTest):
    candidates = []

    def register_probes(self):
        reg.register(
            stub_probe("signoz.error_logs", "telemetry", ["dependency_failure"], "x")
        )

    def setUp(self):
        super().setUp()
        self.topology.stop()
        self.topology = mock.patch.object(
            kernel,
            "run_topology_subagent",
            return_value=TopologyResult(summary="No path found."),
        )
        self.topology.start()

    def test_exits_gracefully_with_no_topology(self):
        out = self.run_graph(service="")
        self.assertFalse(out["verification_result"]["passed"])
        self.assertIn("Insufficient evidence", out_text(out))


def out_text(state) -> str:
    return state["messages"][-1].content


if __name__ == "__main__":
    unittest.main()
