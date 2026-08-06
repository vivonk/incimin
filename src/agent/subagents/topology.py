"""Topology sub-agent (Navigator role). 100% deterministic — no LLM.

Traverses the Memgraph service graph via BFS from the alerting service and returns a ranked
candidate-service list, replacing today's raw path string with a structured hand-off contract
that the Telemetry and Knowledge sub-agents consume (see MULTI_AGENT_ARCHITECTURE.md §3.1, §4).
"""
from dataclasses import dataclass, field

import neo4j

from src.agent.state import Evidence

BFS_QUERY = "MATCH path = (s:Service {name: $source})-[*BFS]->(target) RETURN path LIMIT 10"


@dataclass
class TopologyResult:
    candidate_services: list[str] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    summary: str = ""


def run_topology_subagent(source: str) -> TopologyResult:
    """BFS-traverse from `source` and rank candidates by order of first appearance (BFS depth proxy)."""
    try:
        driver = neo4j.GraphDatabase.driver("bolt://127.0.0.1:7687", auth=("", ""))
        with driver.session() as session:
            records = list(session.run(BFS_QUERY, source=source))
    except Exception as e:
        msg = f"Error executing topology query: {e}"
        return TopologyResult(summary=msg)

    if not records:
        return TopologyResult(summary="No path found.")

    seen_order: list[str] = []
    evidence: list[Evidence] = []
    for idx, record in enumerate(records):
        path = record["path"]
        node_names = [name for name in (_node_name(n) for n in path.nodes) if name]
        for name in node_names:
            if name not in seen_order:
                seen_order.append(name)
        evidence.append(
            {
                "id": f"topology-{idx}",
                "source": "topology",
                "service": node_names[-1] if node_names else source,
                "summary": " -> ".join(node_names) if node_names else str(path),
                "raw": {"path": str(path), "nodes": node_names},
                "timestamp": None,
            }
        )

    # Rank = order of first appearance across BFS results, source excluded — a simple,
    # deterministic fault-gradient proxy per MULTI_AGENT_ARCHITECTURE.md §3.1.
    candidates = [name for name in seen_order if name != source] or seen_order
    summary = f"Traversed {len(records)} path(s) from '{source}'. Candidates: {', '.join(candidates)}"
    return TopologyResult(candidate_services=candidates, evidence=evidence, summary=summary)


def _node_name(node) -> str | None:
    try:
        return node.get("name")
    except AttributeError:
        return None
