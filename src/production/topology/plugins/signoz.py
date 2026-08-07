import logging
import datetime
from typing import AsyncIterator, Any
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from src.production.topology.plugin import PluginConfig, TopologyPlugin
from src.production.topology.models import ServiceNode, ServiceEdge


class SigNozPluginConfig(PluginConfig):
    SIGNOZ_API_URL: str
    SIGNOZ_API_TOKEN: str


class SigNozServiceMap(TopologyPlugin):
    config: SigNozPluginConfig

    def __init__(self, config: SigNozPluginConfig):
        super().__init__(config)
        self.config = config

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(max=30))
    async def _fetch_data(self) -> Any:
        headers = {
            "SigNoz-Api-Key": self.config.SIGNOZ_API_TOKEN,
            "Content-Type": "application/json"
        }
        # Dynamic timestamps (last 1 hour in nanoseconds)
        import time
        now_ns = int(time.time() * 1e9)
        start_ns = now_ns - (3600 * int(1e9))
        payload = {
            "start": str(start_ns),
            "end": str(now_ns),
            "tags": []
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(self.config.SIGNOZ_API_URL, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()

    async def fetch_topology(self) -> AsyncIterator[ServiceNode | ServiceEdge]:
        data = await self._fetch_data()
        
        # The SigNoz dependency graph API returns a list of edges directly
        items = data if isinstance(data, list) else data.get("data", [])
        seen_nodes = set()
        
        for item in items:
            if not isinstance(item, dict):
                continue
                
            parent_name = item.get("parent")
            child_name = item.get("child")
            
            if not parent_name or not child_name:
                logging.warning(f"Skipping malformed entity, missing parent/child: {item}")
                continue
                
            fetched_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            
            # Yield parent node if not seen yet
            if parent_name not in seen_nodes:
                yield ServiceNode(
                    source="signoz",
                    external_id=parent_name,
                    schema_version="1",
                    fetched_at=fetched_at,
                    name=parent_name,
                    attributes={}
                )
                seen_nodes.add(parent_name)
                
            # Yield child node if not seen yet
            if child_name not in seen_nodes:
                yield ServiceNode(
                    source="signoz",
                    external_id=child_name,
                    schema_version="1",
                    fetched_at=fetched_at,
                    name=child_name,
                    attributes={}
                )
                seen_nodes.add(child_name)
                
            # Yield the dependency edge with its metrics (callCount, p99, etc.)
            edge_id = f"{parent_name}->{child_name}"
            attributes = {k: v for k, v in item.items() if k not in ("parent", "child")}
            yield ServiceEdge(
                source="signoz",
                external_id=edge_id,
                schema_version="1",
                fetched_at=fetched_at,
                source_node_id=parent_name,
                target_node_id=child_name,
                attributes=attributes
            )
