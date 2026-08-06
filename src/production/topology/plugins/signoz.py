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
        headers = {"Authorization": f"Bearer {self.config.SIGNOZ_API_TOKEN}"}
        async with httpx.AsyncClient() as client:
            response = await client.get(self.config.SIGNOZ_API_URL, headers=headers)
            response.raise_for_status()
            return response.json()

    async def fetch_topology(self) -> AsyncIterator[ServiceNode | ServiceEdge]:
        data = await self._fetch_data()
        
        # Determine if data is a list or a dict containing lists
        items = []
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get("data", [])
            if not items:
                # maybe nodes and edges?
                nodes = data.get("nodes", [])
                edges = data.get("edges", [])
                items = nodes + edges

        for item in items:
            if not isinstance(item, dict):
                continue
            
            external_id = item.get("external_id") or item.get("id")
            if not external_id:
                logging.warning(f"Skipping malformed entity, missing external_id: {item}")
                continue
                
            fetched_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            
            try:
                # If item has source_node_id and target_node_id, treat it as an edge
                source_id = item.get("source_node_id") or item.get("source")
                target_id = item.get("target_node_id") or item.get("target")
                
                if source_id and target_id:
                    yield ServiceEdge(
                        source="signoz",
                        external_id=str(external_id),
                        schema_version="1",
                        fetched_at=fetched_at,
                        source_node_id=str(source_id),
                        target_node_id=str(target_id),
                        attributes=item.get("attributes", {})
                    )
                else:
                    yield ServiceNode(
                        source="signoz",
                        external_id=str(external_id),
                        schema_version="1",
                        fetched_at=fetched_at,
                        name=item.get("name", "unknown"),
                        attributes=item.get("attributes", {})
                    )
            except Exception as e:
                logging.warning(f"Skipping malformed entity {external_id}: {e}")
                continue
