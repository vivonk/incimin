from neo4j import AsyncGraphDatabase, AsyncDriver
from typing import Optional
from src.production.topology.models import ServiceNode, ServiceEdge

class TopologyRepository:
    def __init__(self, uri: str = "bolt://127.0.0.1:7687", auth: tuple = ("", "")):
        self.uri = uri
        self.auth = auth
        self.driver: Optional[AsyncDriver] = None

    async def connect(self):
        if not self.driver:
            self.driver = AsyncGraphDatabase.driver(self.uri, auth=self.auth)

    async def close(self):
        if self.driver:
            await self.driver.close()
            self.driver = None

    async def upsert_node(self, node: ServiceNode):
        await self.connect()
        query = """
        MERGE (n:Service {internal_id: $internal_id})
        ON CREATE SET 
            n.source = $source,
            n.external_id = $external_id,
            n.fetched_at = $fetched_at,
            n.schema_version = $schema_version,
            n.name = $name,
            n.type = $type
        ON MATCH SET
            n.source = $source,
            n.external_id = $external_id,
            n.fetched_at = $fetched_at,
            n.schema_version = $schema_version,
            n.name = $name,
            n.type = $type
        """
        async with self.driver.session() as session:
            await session.run(
                query,
                internal_id=node.internal_id,
                source=node.source,
                external_id=node.external_id,
                fetched_at=node.fetched_at,
                schema_version=node.schema_version,
                name=node.name,
                type=node.type
            )

    async def upsert_edge(self, edge: ServiceEdge):
        await self.connect()
        query = """
        MATCH (s:Service {internal_id: $source_node_id})
        MATCH (t:Service {internal_id: $target_node_id})
        MERGE (s)-[r:CALLS {internal_id: $internal_id}]->(t)
        ON CREATE SET
            r.source = $source,
            r.external_id = $external_id,
            r.fetched_at = $fetched_at,
            r.schema_version = $schema_version,
            r.type = $type
        ON MATCH SET
            r.source = $source,
            r.external_id = $external_id,
            r.fetched_at = $fetched_at,
            r.schema_version = $schema_version,
            r.type = $type
        """
        async with self.driver.session() as session:
            await session.run(
                query,
                source_node_id=edge.source_node_id,
                target_node_id=edge.target_node_id,
                internal_id=edge.internal_id,
                source=edge.source,
                external_id=edge.external_id,
                fetched_at=edge.fetched_at,
                schema_version=edge.schema_version,
                type=edge.type
            )
