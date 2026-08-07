import pytest
import httpx
from src.production.topology.plugins.signoz import SigNozServiceMap, SigNozPluginConfig
from src.production.topology.models import ServiceNode, ServiceEdge

@pytest.mark.asyncio
async def test_signoz_plugin_fetch(httpx_mock):
    # Mocking the HTTP response
    mock_response = [
        {
            "external_id": "node_1",
            "name": "service-a",
            "attributes": {"env": "prod"}
        },
        {
            "external_id": "edge_1",
            "source_node_id": "node_1",
            "target_node_id": "node_2",
            "attributes": {"latency": "10ms"}
        },
        {
            # Malformed entity (missing external_id)
            "name": "malformed_node",
        },
        {
            "id": "node_2", # fallback for external_id
            "name": "service-b"
        }
    ]
    
    url = "http://signoz-api/topology"
    httpx_mock.add_response(url=url, json=mock_response)
    
    config = SigNozPluginConfig(
        SIGNOZ_API_URL=url,
        SIGNOZ_API_TOKEN="fake-token"
    )
    
    plugin = SigNozServiceMap(config=config)
    
    entities = []
    async for entity in plugin.fetch_topology():
        entities.append(entity)
        
    assert len(entities) == 3
    
    node_1 = entities[0]
    assert isinstance(node_1, ServiceNode)
    assert node_1.external_id == "node_1"
    assert node_1.name == "service-a"
    assert node_1.source == "signoz"
    
    edge_1 = entities[1]
    assert isinstance(edge_1, ServiceEdge)
    assert edge_1.external_id == "edge_1"
    assert edge_1.source_node_id == "node_1"
    assert edge_1.target_node_id == "node_2"
    assert edge_1.source == "signoz"

    node_2 = entities[2]
    assert isinstance(node_2, ServiceNode)
    assert node_2.external_id == "node_2"
    assert node_2.name == "service-b"
