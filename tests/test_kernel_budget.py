"""Adaptive round budget and the four stopping conditions.

The design commitment under test: the loop's continue/stop decision is arithmetic, never a
judgement handed to a model.
"""
import unittest

from src.agent.kernel.beliefs import apply_verdicts, EvidenceVerdict, seed_posteriors
from src.agent.kernel.budget import (
    B_MAX,
    B_MIN,
    converged_on_confidence,
    size_budget,
    stop_reason,
)
from src.agent.kernel.state import Budget, Hypothesis


def h(id_, prior=1.0, service=None):
    return Hypothesis(
        id=id_,
        kind="dependency_failure",
        statement="",
        subject_service=service or id_,
        origin="topology",
        prior=prior,
    )


class TestBudgetSizing(unittest.TestCase):
    def test_single_hypothesis_gets_the_minimum(self):
        self.assertEqual(size_budget(seed_posteriors([h("a")])).max_rounds, B_MIN)

    def test_maximally_ambiguous_field_gets_the_maximum(self):
        budget = size_budget(seed_posteriors([h("a"), h("b"), h("c")]))
        self.assertEqual(budget.max_rounds, B_MAX)

    def test_skewed_field_lands_between(self):
        budget = size_budget(seed_posteriors([h("a", 20.0), h("b", 1.0), h("c", 1.0)]))
        self.assertGreaterEqual(budget.max_rounds, B_MIN)
        self.assertLessEqual(budget.max_rounds, B_MAX)

    def test_budget_is_never_below_the_floor(self):
        self.assertGreaterEqual(size_budget([]).max_rounds, 0)

    def test_exhausted_reflects_rounds_used(self):
        self.assertFalse(Budget(max_rounds=2, rounds_used=1).exhausted)
        self.assertTrue(Budget(max_rounds=2, rounds_used=2).exhausted)


class TestStopping(unittest.TestCase):
    def setUp(self):
        self.open_budget = Budget(max_rounds=5, rounds_used=0)

    def test_keeps_going_while_undecided_and_in_budget(self):
        hs = seed_posteriors([h("a"), h("b")])
        self.assertEqual(stop_reason(hs, self.open_budget), "")

    def test_converges_when_leader_crosses_tau(self):
        hs = seed_posteriors([h("a", 99.0), h("b", 1.0)])
        self.assertEqual(stop_reason(hs, self.open_budget), "converged")

    def test_stops_when_budget_is_exhausted(self):
        hs = seed_posteriors([h("a"), h("b")])
        self.assertEqual(
            stop_reason(hs, Budget(max_rounds=1, rounds_used=1)), "budget_exhausted"
        )

    def test_convergence_beats_exhaustion(self):
        """A run that converges on its final permitted round is converged, not starved."""
        hs = seed_posteriors([h("a", 99.0), h("b", 1.0)])
        self.assertEqual(
            stop_reason(hs, Budget(max_rounds=1, rounds_used=1)), "converged"
        )

    def test_stops_when_everything_is_refuted(self):
        hs = apply_verdicts(
            seed_posteriors([h("a"), h("b")]),
            [
                EvidenceVerdict(hypothesis_id="a", evidence_id="e1", verdict="refutes"),
                EvidenceVerdict(hypothesis_id="b", evidence_id="e2", verdict="refutes"),
            ],
        ).hypotheses
        self.assertEqual(stop_reason(hs, self.open_budget), "all_refuted")

    def test_stops_when_nothing_left_discriminates(self):
        hs = seed_posteriors([h("a"), h("b")])
        self.assertEqual(
            stop_reason(hs, self.open_budget, has_discriminating_probe=False),
            "no_discriminating_probe",
        )

    def test_only_convergence_earns_high_confidence(self):
        self.assertTrue(converged_on_confidence("converged"))
        self.assertFalse(converged_on_confidence("budget_exhausted"))
        self.assertFalse(converged_on_confidence("no_discriminating_probe"))
        self.assertFalse(converged_on_confidence(""))


if __name__ == "__main__":
    unittest.main()
