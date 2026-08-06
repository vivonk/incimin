"""Knowledge sub-agent (Retriever role). Deterministic fast path by default, with a bounded
(single-call, no loop) LLM re-rank when the vector search's top match is low-confidence — per
MULTI_AGENT_ARCHITECTURE.md §3.1's "deterministic-by-default, LLM as an escape hatch" recommendation.
"""
from dataclasses import dataclass, field

from fastembed import TextEmbedding
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient

from src.agent.llm import build_llm
from src.agent.state import Evidence

RELEVANCE_THRESHOLD = 0.5


class RerankSelection(BaseModel):
    """Bounded LLM output: pick from the already-fetched candidates, don't generate new queries."""

    selected_ids: list[str] = Field(default_factory=list)
    reason: str = ""


@dataclass
class KnowledgeResult:
    evidence: list[Evidence] = field(default_factory=list)
    summary: str = ""


def run_knowledge_subagent(query: str, top_k: int = 3) -> KnowledgeResult:
    try:
        client = QdrantClient("http://127.0.0.1:6333", timeout=5.0)
        embedding_model = TextEmbedding("BAAI/bge-small-en-v1.5")
        embeddings = list(embedding_model.embed([query]))
        results = client.query_points(
            collection_name="runbooks", query=embeddings[0].tolist(), limit=max(top_k, 5)
        )
    except Exception as e:
        return KnowledgeResult(summary=f"Error executing knowledge query: {e}")

    points = results.points or []
    if not points:
        return KnowledgeResult(summary="No runbooks found.")

    candidates: list[Evidence] = []
    for i, point in enumerate(points):
        payload = point.payload or {}
        filename = payload.get("filename", "unknown")
        candidates.append(
            {
                "id": f"knowledge-{i}",
                "source": "knowledge",
                "service": _service_from_filename(filename),
                "summary": filename,
                "raw": {"filename": filename, "content": payload.get("content", ""), "score": point.score},
                "timestamp": None,
            }
        )

    top_score = candidates[0]["raw"]["score"]
    if top_score >= RELEVANCE_THRESHOLD or len(candidates) == 1:
        chosen = candidates[:top_k]
        return KnowledgeResult(evidence=chosen, summary=f"Top match: {chosen[0]['summary']} (score={top_score:.2f}).")

    # Ambiguous top match — one bounded LLM call re-ranks the already-fetched candidates.
    selection = _rerank(query, candidates)
    chosen = [c for c in candidates if c["id"] in selection.selected_ids] or candidates[:top_k]
    return KnowledgeResult(
        evidence=chosen, summary=f"Re-ranked {len(candidates)} low-confidence match(es). ({selection.reason})"
    )


def _service_from_filename(filename: str) -> str:
    return filename.replace(".md", "").split("_")[0] if filename else "unknown"


def _rerank(query: str, candidates: list[Evidence]) -> RerankSelection:
    try:
        structured = build_llm().with_structured_output(RerankSelection)
        listing = "\n".join(
            f"- {c['id']}: {c['summary']} (score={c['raw']['score']:.2f})" for c in candidates
        )
        prompt = (
            f"Incident query: {query}\nCandidate runbooks (low-confidence vector match):\n{listing}\n"
            "Select the id(s) of the runbook(s) actually relevant to this incident, most relevant first."
        )
        return structured.invoke(prompt)
    except Exception as e:
        return RerankSelection(
            selected_ids=[candidates[0]["id"]] if candidates else [],
            reason=f"LLM re-rank unavailable ({e}); defaulting to top match.",
        )
