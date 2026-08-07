import clickhouse_connect
from neo4j import AsyncGraphDatabase
import uuid
import datetime
import asyncio

def _insert_ch(query: str):
    import subprocess
    code = f"""
import clickhouse_connect
client = clickhouse_connect.get_client(host='127.0.0.1', port=8123)
client.command('''{query}''')
"""
    import sys
    subprocess.run([sys.executable, "-c", code], check=True)

async def insert_webhook_event(repo_url: str, commit_sha: str, service_name: str, event_time: str):
    ext_id = str(uuid.uuid4())
    query = f"""
    INSERT INTO system_changes (timestamp, repository_url, commit_sha, service_name, source, external_id, fetched_at, schema_version)
    VALUES ('{event_time}', '{repo_url}', '{commit_sha}', '{service_name}', 'webhook_simulation', '{ext_id}', now(), '1.0')
    """
    await asyncio.to_thread(_insert_ch, query)

async def merge_deployment_event(repo_url: str, service_name: str):
    now_str = datetime.datetime.now().isoformat()
    # Deterministic UUIDs to ensure stable entity metadata
    repo_ext_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"repo:{repo_url}"))
    svc_ext_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"svc:{service_name}"))
    rel_ext_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"rel:{repo_url}:{service_name}"))
    
    query = f"""
    MERGE (r:Repository {{url: $repo}})
    ON CREATE SET r.source = 'webhook_simulation',
                  r.external_id = '{repo_ext_id}',
                  r.schema_version = '1.0'
    SET r.fetched_at = '{now_str}'
        
    MERGE (s:Service {{name: $service}})
    ON CREATE SET s.source = 'webhook_simulation',
                  s.external_id = '{svc_ext_id}',
                  s.schema_version = '1.0'
    SET s.fetched_at = '{now_str}'
        
    MERGE (r)-[rel:DEPLOYS_TO]->(s)
    ON CREATE SET rel.source = 'webhook_simulation',
                  rel.external_id = '{rel_ext_id}',
                  rel.schema_version = '1.0'
    SET rel.fetched_at = '{now_str}'
    """
    driver = AsyncGraphDatabase.driver("bolt://127.0.0.1:7687", auth=("", ""))
    async with driver.session() as session:
        await session.run(query, repo=repo_url, service=service_name)
    await driver.close()

async def insert_pr_merge_event(repo_url: str, pr_number: int, commit_sha: str, author: str, service_name: str, event_time: str):
    ext_id = str(uuid.uuid4())
    query = f"""
    INSERT INTO system_changes (timestamp, repository_url, commit_sha, service_name, source, external_id, fetched_at, schema_version)
    VALUES ('{event_time}', '{repo_url}', '{commit_sha}', '{service_name}', 'github_webhook', '{ext_id}', now(), '1.0')
    """
    await asyncio.to_thread(_insert_ch, query)


