"""Probe registration and per-team resolution.

This replaces `src/production/topology/manager.py`, keeping its good ideas and fixing three
things that would not survive teams contributing probes:

  - **Validation happened at the wrong end.** `register_plugin` accepted anything and only
    `get_plugin_class` checked the type, so a broken plugin registered cleanly and failed at
    the point of use. Validation now happens at registration.
  - **The registry was a module-level dict with no tenancy.** Nothing bound a plugin to a team.
    `registry_for_team` now returns a resolved, filtered view.
  - **Plugins carried no metadata.** No name, version, or capability declaration meant the host
    could not check a plugin before instantiating it. That is what `ProbeManifest` is for.
"""
import logging
from typing import Iterable

from src.agent.kernel.state import BASE_HYPOTHESIS_KINDS
from src.agent.probes.base import Probe, ProbeManifest

log = logging.getLogger("incimin.probes")

_PROBES: dict[str, Probe] = {}
_KINDS: set[str] = set(BASE_HYPOTHESIS_KINDS)
_SOURCES: dict[str, set[str]] = {}  # source -> probe ids emitting it


class ProbeRegistrationError(ValueError):
    """Raised at registration, deliberately — never deferred to call time."""


def register(probe: Probe, *, replace: bool = False) -> Probe:
    """Validate and register a probe. Usable as a decorator on an instance factory."""
    manifest: ProbeManifest = probe.manifest

    if not isinstance(manifest, ProbeManifest):
        raise ProbeRegistrationError(f"{probe!r} has no ProbeManifest")
    if not manifest.id or "." not in manifest.id:
        raise ProbeRegistrationError(f"probe id {manifest.id!r} must be namespaced, e.g. 'signoz.error_logs'")
    if manifest.id in _PROBES and not replace:
        raise ProbeRegistrationError(f"probe id {manifest.id!r} is already registered")
    if manifest.owner == "team" and not manifest.team:
        raise ProbeRegistrationError(f"probe {manifest.id!r} declares owner='team' but no team")
    if not hasattr(probe, "run"):
        raise ProbeRegistrationError(f"probe {manifest.id!r} does not implement run()")

    # A probe may discriminate kinds it declares itself, but not kinds nobody has defined —
    # that is almost always a typo, and a typo here silently makes the probe unselectable.
    known = _KINDS | set(manifest.declares_kinds)
    unknown = [k for k in manifest.discriminates if k not in known]
    if unknown:
        raise ProbeRegistrationError(
            f"probe {manifest.id!r} discriminates unknown hypothesis kinds {unknown}; "
            f"declare them in `declares_kinds` or use one of {sorted(known)}"
        )

    _KINDS.update(manifest.declares_kinds)
    _SOURCES.setdefault(manifest.source, set()).add(manifest.id)
    _PROBES[manifest.id] = probe
    log.debug("registered probe %s (source=%s, owner=%s)", manifest.id, manifest.source, manifest.owner)
    return probe


def known_sources() -> set[str]:
    """Valid values for `Evidence.source`. This is where the v1 `Literal` constraint went."""
    return set(_SOURCES)


def known_kinds() -> set[str]:
    return set(_KINDS)


def all_probes() -> dict[str, Probe]:
    return dict(_PROBES)


def reset() -> None:
    """Test isolation. The old registry leaked registrations across tests because it had no
    teardown path and tests wrote straight into the module global."""
    _PROBES.clear()
    _SOURCES.clear()
    _KINDS.clear()
    _KINDS.update(BASE_HYPOTHESIS_KINDS)


class ProbeRegistry:
    """A team's resolved probe roster. Immutable once built."""

    def __init__(self, team_id: str, probes: dict[str, Probe]):
        self.team_id = team_id
        self._probes = probes

    def __len__(self) -> int:
        return len(self._probes)

    def __contains__(self, probe_id: object) -> bool:
        return probe_id in self._probes

    def get(self, probe_id: str) -> Probe | None:
        return self._probes.get(probe_id)

    def manifests(self) -> list[ProbeManifest]:
        """Manifest order is registration order, which is what makes selection tie-breaking
        stable and therefore the golden path replayable."""
        return [p.manifest for p in self._probes.values()]

    def ids(self) -> list[str]:
        return list(self._probes)


def registry_for_team(team_id: str, *, allowlist: Iterable[str] | None = None) -> ProbeRegistry:
    """Core probes plus this team's own, optionally narrowed by the team's allowlist.

    A team never sees another team's probes: that is the isolation boundary, and it is enforced
    here rather than by prompt instructions telling a model not to call something.
    """
    allowed = set(allowlist) if allowlist is not None else None
    resolved: dict[str, Probe] = {}
    for probe_id, probe in _PROBES.items():
        m = probe.manifest
        if m.owner == "team" and m.team != team_id:
            continue
        if allowed is not None and probe_id not in allowed:
            continue
        resolved[probe_id] = probe
    return ProbeRegistry(team_id, resolved)
