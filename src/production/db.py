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

async def insert_webhook_event(repo_url: str, commit_sha: str, service_name: str):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ext_id = str(uuid.uuid4())
    query = f"""
    INSERT INTO system_changes (timestamp, repository_url, commit_sha, service_name, source, external_id, fetched_at, schema_version)
    VALUES (now(), '{repo_url}', '{commit_sha}', '{service_name}', 'webhook_simulation', '{ext_id}', now(), '1.0')
    """
    await asyncio.to_thread(_insert_ch, query)

async def merge_deployment_event(repo_url: str, service_name: str):
    now_str = datetime.datetime.now().isoformat()
    query = f"""
    MERGE (r:Repository {{url: $repo}})
    SET r.source = 'webhook_simulation',
        r.external_id = '{str(uuid.uuid4())}',
        r.fetched_at = '{now_str}',
        r.schema_version = '1.0'
        
    MERGE (s:Service {{name: $service}})
    SET s.source = 'webhook_simulation',
        s.external_id = '{str(uuid.uuid4())}',
        s.fetched_at = '{now_str}',
        s.schema_version = '1.0'
        
    MERGE (r)-[rel:DEPLOYS_TO]->(s)
    SET rel.source = 'webhook_simulation',
        rel.external_id = '{str(uuid.uuid4())}',
        rel.fetched_at = '{now_str}',
        rel.schema_version = '1.0'
    """
    driver = AsyncGraphDatabase.driver("bolt://127.0.0.1:7687", auth=("", ""))
    async with driver.session() as session:
        await session.run(query, repo=repo_url, service=service_name)
    await driver.close()

async def insert_pr_merge_event(repo_url: str, pr_number: int, commit_sha: str, author: str, service_name: str):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ext_id = str(uuid.uuid4())
    query = f"""
    INSERT INTO system_changes (timestamp, repository_url, commit_sha, service_name, source, external_id, fetched_at, schema_version)
    VALUES (now(), '{repo_url}', '{commit_sha}', '{service_name}', 'github_webhook', '{ext_id}', now(), '1.0')
    """
    await asyncio.to_thread(_insert_ch, query)


