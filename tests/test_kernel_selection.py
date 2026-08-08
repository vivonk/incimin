"""Probe registry and discriminating-test selection.

The property under test throughout: selection is a deterministic table join. Given the same
hypotheses and the same roster, it must pick the same probes in the same order, forever.
"""
import unittest
from typing import ClassVar

from src.agent.kernel.beliefs import seed_posteriors
from src.agent.kernel.selection import discrimination_score, rank_probes, select_probes
from src.agent.kernel.state import Hypothesis
from src.agent.probes import registry as reg
from src.agent.probes.base import ProbeManifest, ProbeRequest, ProbeResult, TimeWindow

FIXED_NOW_NS = 1_800_000_000_000_000_000


def make_probe(probe_id, source, discriminates, cost="cheap", owner="core", team=None, kinds=()):
    class _P:
        manifest: ClassVar[ProbeManifest] = ProbeManifest(
            id=probe_id,
            source=source,
            discriminates=list(discriminates),
            cost_tier=cost,
            owner=owner,
            team=team,
            declares_kinds=list(kinds),
        )

        async def run(self, req: ProbeRequest) -> ProbeResult:
            return ProbeResult.nothing("stub")

    return _P()


def h(id_, kind, service="svc", prior=1.0):
    return Hypothesis(
        id=id_, kind=kind, statement="", subject_service=service, origin="topology", prior=prior
    )


class TestRegistry(unittest.TestCase):
    def setUp(self):
        reg.reset()

    def tearDown(self):
        reg.reset()

    def test_rejects_unnamespaced_id(self):
        with self.assertRaises(reg.ProbeRegistrationError):
            reg.register(make_probe("logs", "telemetry", ["data_issue"]))

    def test_rejects_duplicate_id(self):
        reg.register(make_probe("a.b", "telemetry", ["data_issue"]))
        with self.assertRaises(reg.ProbeRegistrationError):
            reg.register(make_probe("a.b", "telemetry", ["data_issue"]))

    def test_replace_allows_reregistration(self):
        reg.register(make_probe("a.b", "telemetry", ["data_issue"]))
        reg.register(make_probe("a.b", "telemetry", ["data_issue"]), replace=True)
        self.assertEqual(len(reg.all_probes()), 1)

    def test_rejects_unknown_hypothesis_kind(self):
        """A typo in `discriminates` would otherwise make the probe silently unselectable."""
        with self.assertRaises(reg.ProbeRegistrationError):
            reg.register(make_probe("a.b", "telemetry", ["depoy_regression"]))

    def test_probe_may_declare_its_own_kind(self):
        reg.register(
            make_probe("team.flags", "flags", ["flag_rollout"], kinds=["flag_rollout"])
        )
        self.assertIn("flag_rollout", reg.known_kinds())

    def test_team_owner_requires_a_team(self):
        with self.assertRaises(reg.ProbeRegistrationError):
            reg.register(make_probe("t.p", "x", ["data_issue"], owner="team", team=None))

    def test_registration_validates_eagerly_not_at_call_time(self):
        """The v1.6 plugin manager accepted anything and only failed on retrieval."""
        class NotAProbe:
            manifest = ProbeManifest(id="x.y", source="s")

        with self.assertRaises(reg.ProbeRegistrationError):
            reg.register(NotAProbe())

    def test_source_registry_replaces_the_v1_literal(self):
        reg.register(make_probe("a.b", "telemetry", ["data_issue"]))
        reg.register(make_probe("c.d", "flags", ["data_issue"]))
        self.assertEqual(reg.known_sources(), {"telemetry", "flags"})


class TestTeamScoping(unittest.TestCase):
    def setUp(self):
        reg.reset()
        reg.register(make_probe("core.logs", "telemetry", ["data_issue"]))
        reg.register(make_probe("pay.flags", "flags", ["config_change"], owner="team", team="payments"))
        reg.register(make_probe("cart.x", "custom", ["config_change"], owner="team", team="cart"))

    def tearDown(self):
        reg.reset()

    def test_team_sees_core_plus_its_own(self):
        self.assertEqual(set(reg.registry_for_team("payments").ids()), {"core.logs", "pay.flags"})

    def test_team_cannot_see_another_teams_probe(self):
        self.assertNotIn("cart.x", reg.registry_for_team("payments"))

    def test_allowlist_narrows_further(self):
        r = reg.registry_for_team("payments", allowlist=["core.logs"])
        self.assertEqual(r.ids(), ["core.logs"])


class TestDiscrimination(unittest.TestCase):
    def test_probe_addressing_exactly_one_kind_discriminates(self):
        m = make_probe("a.b", "changes", ["deploy_regression"]).manifest
        self.assertEqual(discrimination_score(m, "deploy_regression", "dependency_failure"), 1.0)

    def test_probe_addressing_both_kinds_does_not_discriminate(self):
        m = make_probe("a.b", "x", ["deploy_regression", "dependency_failure"]).manifest
        self.assertEqual(discrimination_score(m, "deploy_regression", "dependency_failure"), 0.0)

    def test_probe_addressing_neither_kind_does_not_discriminate(self):
        m = make_probe("a.b", "x", ["data_issue"]).manifest
        self.assertEqual(discrimination_score(m, "deploy_regression", "dependency_failure"), 0.0)


class TestSelection(unittest.TestCase):
    def setUp(self):
        reg.reset()
        reg.register(make_probe("signoz.logs", "telemetry", ["dependency_failure"], cost="cheap"))
        reg.register(make_probe("changes.deploys", "changes", ["deploy_regression"], cost="cheap"))
        reg.register(make_probe("deep.trace", "traces", ["deploy_regression"], cost="expensive"))
        self.registry = reg.registry_for_team("default")
        self.hypotheses = seed_posteriors(
            [h("a", "deploy_regression", "pay"), h("b", "dependency_failure", "cart")]
        )

    def tearDown(self):
        reg.reset()

    def _select(self, **kw):
        defaults = dict(
            hypotheses=self.hypotheses,
            registry=self.registry,
            seen_keys=[],
            round_index=1,
            services=["pay"],
            now_ns=FIXED_NOW_NS,
        )
        return select_probes(**{**defaults, **kw})

    def test_round_zero_runs_cheap_breadth(self):
        chosen = [r.probe_id for r in self._select(round_index=0)]
        self.assertEqual(set(chosen), {"signoz.logs", "changes.deploys"})
        self.assertNotIn("deep.trace", chosen)

    def test_later_rounds_prefer_cheap_over_expensive_when_both_discriminate(self):
        ranked = rank_probes(self.hypotheses, self.registry)
        order = [m.id for m, score in ranked if score > 0]
        self.assertLess(order.index("changes.deploys"), order.index("deep.trace"))

    def test_dedup_excludes_an_already_asked_question(self):
        first = self._select()
        self.assertTrue(first)
        again = self._select(seen_keys=[r.dedup_key for r in first])
        self.assertEqual(again, [])

    def test_selection_is_stable_across_runs(self):
        runs = {tuple(r.probe_id for r in self._select()) for _ in range(5)}
        self.assertEqual(len(runs), 1)

    def test_max_parallel_caps_fanout(self):
        self.assertLessEqual(len(self._select(round_index=0, max_parallel=1)), 1)

    def test_single_surviving_hypothesis_still_gathers_corroboration(self):
        """With nothing to discriminate against, fall back to cost order rather than stalling."""
        solo = seed_posteriors([h("a", "deploy_regression", "pay")])
        self.assertTrue(self._select(hypotheses=solo))


class TestDedupKey(unittest.TestCase):
    def _req(self, **kw):
        defaults = dict(
            probe_id="a.b",
            services=["x"],
            window=TimeWindow.lookback(30, end_ns=FIXED_NOW_NS),
        )
        return ProbeRequest(**{**defaults, **kw})

    def test_same_question_same_key(self):
        self.assertEqual(self._req().dedup_key, self._req().dedup_key)

    def test_service_order_does_not_matter(self):
        a = self._req(services=["x", "y"])
        b = self._req(services=["y", "x"])
        self.assertEqual(a.dedup_key, b.dedup_key)

    def test_moving_window_bounds_do_not_break_dedup(self):
        """Bounds shift every round because end is wall-clock now. If they were part of the
        key, every key would be unique and dedup would silently never fire."""
        a = self._req(window=TimeWindow.lookback(30, end_ns=FIXED_NOW_NS))
        b = self._req(window=TimeWindow.lookback(30, end_ns=FIXED_NOW_NS + 10**11))
        self.assertEqual(a.dedup_key, b.dedup_key)

    def test_broadening_the_window_is_a_different_question(self):
        a = self._req(window=TimeWindow.lookback(30, end_ns=FIXED_NOW_NS))
        b = self._req(window=TimeWindow.lookback(90, end_ns=FIXED_NOW_NS))
        self.assertNotEqual(a.dedup_key, b.dedup_key)


if __name__ == "__main__":
    unittest.main()
