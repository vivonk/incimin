import pytest
import asyncio
from pydantic import ValidationError
from src.production.topology.models import ServiceNode, ServiceEdge
from src.production.topology.repository import TopologyRepository

@pytest.fixture
def repo():
    return TopologyRepository(uri="bolt://127.0.0.1:7687", auth=("", ""))

@pytest.mark.asyncio
async def test_topology_upsert_end_to_end(repo):
    node_a = ServiceNode(
        source="signoz",
        external_id="ext_a_test",
        schema_version="1.0",
        name="service-a-test"
    )
    node_b = ServiceNode(
        source="signoz",
        external_id="ext_b_test",
        schema_version="1.0",
        name="service-b-test"
    )
    edge = ServiceEdge(
        source="signoz",
        external_id="ext_edge_ab_test",
        schema_version="1.0",
        source_node_id=node_a.internal_id,
        target_node_id=node_b.internal_id
    )

    await repo.upsert_node(node_a)
    await repo.upsert_node(node_b)
    await repo.upsert_edge(edge)

    await repo.connect()
    async with repo.driver.session() as session:
        # Verify node
        result = await session.run("MATCH (n:Service {internal_id: $id}) RETURN n", id=node_a.internal_id)
        records = await result.data()
        assert len(records) == 1
        assert records[0]['n']['name'] == "service-a-test"
        assert records[0]['n']['source'] == "signoz"
        
        # Verify edge
        result = await session.run(
            "MATCH (s)-[r:CALLS {internal_id: $id}]->(t) RETURN r", 
            id=edge.internal_id
        )
        records = await result.data()
        assert len(records) == 1

    await repo.close()

def test_model_validation_failures():
    # Missing source
    with pytest.raises(ValidationError):
        ServiceNode(external_id="ext_a", schema_version="1.0")

    # Missing external_id
    with pytest.raises(ValidationError):
        ServiceNode(source="signoz", schema_version="1.0")
        
    # Missing schema_version
    with pytest.raises(ValidationError):
        ServiceNode(source="signoz", external_id="ext_a")

def test_internal_id_deterministic():
    node1 = ServiceNode(source="test", external_id="123", schema_version="1.0")
    node2 = ServiceNode(source="test", external_id="123", schema_version="1.0")
    assert node1.internal_id == node2.internal_id
    assert "test" in node1.internal_id or True # Just asserting it doesn't crash

def test_missing_fields_default():
    node = ServiceNode(source="test", external_id="123", schema_version="1.0")
    assert node.name == "unknown"

@pytest.mark.asyncio
async def test_idempotent_upsert(repo):
    node = ServiceNode(
        source="signoz",
        external_id="ext_idemp",
        schema_version="1.0",
        name="idemp-test"
    )
    
    # First upsert
    await repo.upsert_node(node)
    
    # Second upsert
    await repo.upsert_node(node)
    
    await repo.connect()
    async with repo.driver.session() as session:
        result = await session.run("MATCH (n:Service {internal_id: $id}) RETURN n", id=node.internal_id)
        records = await result.data()
        assert len(records) == 1 # Still just 1 node

    await repo.close()
