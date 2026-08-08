"""Which probe to run next.

The counterintuitive rule the diagnosis literature is unanimous on: pick the test that best
*separates* the leading hypotheses, not the one most likely to confirm the leader. Confirmatory
probing is how an agent talks itself into its first guess.

Selection is a table join over probe manifests — no model call on the common path. That is what
makes the golden path replayable, and it is also what lets a team-contributed probe participate
in routing the moment it registers, without anyone editing a prompt.
"""
import logging

from src.agent.kernel.beliefs import top_two
from src.agent.kernel.state import Hypothesis
from src.agent.probes.base import COST_WEIGHT, ProbeManifest, ProbeRequest, TimeWindow
from src.agent.probes.registry import ProbeRegistry

log = logging.getLogger("incimin.selection")

MAX_PARALLEL_PROBES = 4


def discrimination_score(manifest: ProbeManifest, kind_a: str, kind_b: str) -> float:
    """1 if the probe speaks to exactly one of the two competing kinds, else 0.

    A probe that addresses both equally cannot separate them, and neither can one that
    addresses neither — both correctly score zero.
    """
    a = kind_a in manifest.discriminates
    b = kind_b in manifest.discriminates
    return abs(float(a) - float(b))


def rank_probes(
    hypotheses: list[Hypothesis], registry: ProbeRegistry
) -> list[tuple[ProbeManifest, float]]:
    """Score every probe in the roster against the top-two open hypotheses.

    Ties are broken by manifest order (registration order), never by anything time- or
    hash-dependent — that stability is what the golden path's determinism rests on.
    """
    contenders = top_two(hypotheses)
    if len(contenders) < 2:
        # Nothing to discriminate between: one hypothesis left standing, or none. Fall back to
        # cost order so the loop can still gather corroboration cheaply.
        return [(m, 1.0 / COST_WEIGHT[m.cost_tier]) for m in registry.manifests()]

    kind_a, kind_b = contenders[0].kind, contenders[1].kind
    scored = [
        (m, discrimination_score(m, kind_a, kind_b) / COST_WEIGHT[m.cost_tier])
        for m in registry.manifests()
    ]
    return sorted(scored, key=lambda pair: -pair[1])


def select_probes(
    *,
    hypotheses: list[Hypothesis],
    registry: ProbeRegistry,
    seen_keys: list[str],
    round_index: int,
    services: list[str],
    window_minutes: int = 30,
    required_probe_ids: list[str] | None = None,
    max_parallel: int = MAX_PARALLEL_PROBES,
    now_ns: int | None = None,
) -> list[ProbeRequest]:
    """Build this round's probe requests.

    Round 0 runs cheap breadth — every `cost_tier: cheap` probe plus anything the matched
    playbook explicitly asked for — because at that point every hypothesis is still a guess and
    discrimination scores carry no information. Later rounds run only what discriminates.
    """
    seen = set(seen_keys)
    window = TimeWindow.lookback(window_minutes, end_ns=now_ns)
    required = set(required_probe_ids or [])

    if round_index == 0:
        chosen = [
            m for m in registry.manifests() if m.cost_tier == "cheap" or m.id in required
        ]
    else:
        chosen = [m for m, score in rank_probes(hypotheses, registry) if score > 0]

    open_ids = [h.id for h in hypotheses if h.status != "refuted"]
    requests: list[ProbeRequest] = []
    for manifest in chosen:
        req = ProbeRequest(
            probe_id=manifest.id,
            hypothesis_ids=open_ids,
            services=services,
            window=window,
            round_index=round_index,
        )
        if req.dedup_key in seen:
            log.debug("skipping %s — already asked this round-invariant question", manifest.id)
            continue
        requests.append(req)
        if len(requests) >= max_parallel:
            break

    return requests
