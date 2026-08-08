"""Belief arithmetic is pure and table-driven — no LLM, no clock, no I/O.

That property is the point of `kernel/beliefs.py`: if these tests need a model or a network,
the design has leaked.
"""
import unittest

from src.agent.kernel.beliefs import (
    LIKELIHOOD_RATIO,
    EvidenceVerdict,
    apply_verdicts,
    leader,
    normalized_entropy,
    seed_posteriors,
    top_two,
)
from src.agent.kernel.state import Hypothesis


def h(id_, service, prior=1.0, kind="dependency_failure"):
    return Hypothesis(
        id=id_,
        kind=kind,
        statement=f"{service} is the cause",
        subject_service=service,
        origin="topology",
        prior=prior,
    )


def v(hid, eid, verdict):
    return EvidenceVerdict(hypothesis_id=hid, evidence_id=eid, verdict=verdict)


class TestSeeding(unittest.TestCase):
    def test_priors_normalize_to_one(self):
        seeded = seed_posteriors([h("a", "x", 3.0), h("b", "y", 1.0)])
        self.assertAlmostEqual(sum(x.posterior for x in seeded), 1.0)
        self.assertAlmostEqual(seeded[0].posterior, 0.75)

    def test_zero_priors_fall_back_to_uniform(self):
        seeded = seed_posteriors([h("a", "x", 0.0), h("b", "y", 0.0)])
        self.assertAlmostEqual(seeded[0].posterior, 0.5)
        self.assertAlmostEqual(seeded[1].posterior, 0.5)

    def test_seeding_does_not_mutate_input(self):
        original = [h("a", "x", 3.0)]
        seed_posteriors(original)
        self.assertEqual(original[0].posterior, 0.0)


class TestVerdicts(unittest.TestCase):
    def setUp(self):
        self.hypotheses = seed_posteriors([h("a", "x"), h("b", "y")])

    def test_support_shifts_mass_toward_the_supported_hypothesis(self):
        out = apply_verdicts(self.hypotheses, [v("a", "e1", "supports")])
        by_id = {x.id: x for x in out.hypotheses}
        self.assertGreater(by_id["a"].posterior, by_id["b"].posterior)
        self.assertAlmostEqual(sum(x.posterior for x in out.hypotheses), 1.0)

    def test_refutation_eliminates_and_redistributes(self):
        out = apply_verdicts(self.hypotheses, [v("a", "e1", "refutes")])
        by_id = {x.id: x for x in out.hypotheses}
        self.assertEqual(by_id["a"].status, "refuted")
        self.assertEqual(by_id["a"].posterior, 0.0)
        self.assertAlmostEqual(by_id["b"].posterior, 1.0)

    def test_refuted_hypothesis_cannot_be_resurrected(self):
        once = apply_verdicts(self.hypotheses, [v("a", "e1", "refutes")])
        twice = apply_verdicts(once.hypotheses, [v("a", "e2", "strongly_supports")])
        by_id = {x.id: x for x in twice.hypotheses}
        self.assertEqual(by_id["a"].status, "refuted")
        self.assertEqual(by_id["a"].posterior, 0.0)
        self.assertTrue(any("already refuted" in r for r in twice.rejected_verdicts))

    def test_duplicate_verdict_is_rejected_not_double_counted(self):
        once = apply_verdicts(self.hypotheses, [v("a", "e1", "supports")])
        twice = apply_verdicts(once.hypotheses, [v("a", "e1", "supports")])
        self.assertAlmostEqual(
            {x.id: x for x in once.hypotheses}["a"].posterior,
            {x.id: x for x in twice.hypotheses}["a"].posterior,
        )
        self.assertTrue(any("duplicate" in r for r in twice.rejected_verdicts))

    def test_unknown_hypothesis_is_rejected(self):
        out = apply_verdicts(self.hypotheses, [v("nope", "e1", "supports")])
        self.assertTrue(any("unknown hypothesis" in r for r in out.rejected_verdicts))

    def test_supporting_and_refuting_refs_are_tracked(self):
        out = apply_verdicts(
            self.hypotheses, [v("a", "e1", "supports"), v("b", "e2", "weakens")]
        )
        by_id = {x.id: x for x in out.hypotheses}
        self.assertEqual(by_id["a"].supporting_refs, ["e1"])
        self.assertEqual(by_id["b"].refuting_refs, ["e2"])
        # `weakens` records contradicting evidence without eliminating the hypothesis.
        self.assertEqual(by_id["b"].status, "open")

    def test_all_refuted_leaves_no_leader(self):
        out = apply_verdicts(
            self.hypotheses, [v("a", "e1", "refutes"), v("b", "e2", "refutes")]
        )
        self.assertIsNone(leader(out.hypotheses))

    def test_ratios_are_ordered(self):
        self.assertGreater(LIKELIHOOD_RATIO["strongly_supports"], LIKELIHOOD_RATIO["supports"])
        self.assertEqual(LIKELIHOOD_RATIO["neutral"], 1.0)
        self.assertLess(LIKELIHOOD_RATIO["weakens"], 1.0)
        self.assertLess(LIKELIHOOD_RATIO["refutes"], LIKELIHOOD_RATIO["weakens"])

    def test_update_is_deterministic_across_repeated_runs(self):
        runs = [
            [round(x.posterior, 12) for x in apply_verdicts(
                self.hypotheses, [v("a", "e1", "supports"), v("b", "e2", "weakens")]
            ).hypotheses]
            for _ in range(5)
        ]
        self.assertEqual(len(set(map(tuple, runs))), 1)


class TestRanking(unittest.TestCase):
    def test_leader_breaks_ties_on_id(self):
        tied = seed_posteriors([h("b", "y"), h("a", "x")])
        self.assertEqual(leader(tied).id, "b")

    def test_top_two_excludes_refuted(self):
        hs = apply_verdicts(
            seed_posteriors([h("a", "x"), h("b", "y"), h("c", "z")]),
            [v("b", "e1", "refutes")],
        ).hypotheses
        self.assertEqual({x.id for x in top_two(hs)}, {"a", "c"})


class TestEntropy(unittest.TestCase):
    def test_uniform_is_maximally_ambiguous(self):
        self.assertAlmostEqual(
            normalized_entropy(seed_posteriors([h("a", "x"), h("b", "y")])), 1.0
        )

    def test_single_hypothesis_is_unambiguous(self):
        self.assertEqual(normalized_entropy(seed_posteriors([h("a", "x")])), 0.0)

    def test_skewed_distribution_is_between(self):
        skewed = normalized_entropy(seed_posteriors([h("a", "x", 9.0), h("b", "y", 1.0)]))
        self.assertGreater(skewed, 0.0)
        self.assertLess(skewed, 1.0)


if __name__ == "__main__":
    unittest.main()
