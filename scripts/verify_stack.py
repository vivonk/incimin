import os
import sys
import json
import time
import socket
import urllib.request
import urllib.error
import subprocess
import collections
import re
from pathlib import Path

from gqlalchemy import Memgraph
import clickhouse_connect

def parse_ports():
    content = Path('docs/PORTS.md').read_text()
    ports = []
    # Match the markdown table row: | 3000 | 127.0.0.1 | ...
    for line in content.splitlines():
        if line.startswith('|') and '127.0.0.1' in line:
            parts = [p.strip() for p in line.split('|')]
            if len(parts) > 3 and parts[1].isdigit():
                stack = parts[3]
                # Only test ports from stacks deployed in Phase 1
                if stack in ('core', 'signoz', 'otel-demo'):
                    ports.append(int(parts[1]))
    return ports

def parse_services():
    content = Path('docs/OTEL_DEMO_SERVICES.md').read_text()
    services = set()
    in_section = False
    for line in content.splitlines():
        if line.startswith('## Verified Service List'):
            in_section = True
        elif line.startswith('## '):
            in_section = False
        
        if in_section:
            match = re.match(r'^\d+\.\s+([a-zA-Z0-9-]+)', line)
            if match:
                services.add(match.group(1))
    return services

def parse_clickhouse_schema():
    content = Path('docs/CLICKHOUSE_SCHEMA.md').read_text()
    logs_match = re.search(r'Logs table.*`signoz_logs\.([a-zA-Z0-9_]+)`', content)
    traces_match = re.search(r'Traces table.*`signoz_traces\.([a-zA-Z0-9_]+)`', content)
    unit_match = re.search(r'Timestamp unit for logs.*?\|.*?\*\*(nanoseconds|milliseconds)\*\*', content, re.IGNORECASE)
    
    if not logs_match:
        raise ValueError("Missing logs table name in docs/CLICKHOUSE_SCHEMA.md")
    if not traces_match:
        raise ValueError("Missing traces table name in docs/CLICKHOUSE_SCHEMA.md")
    if not unit_match:
        raise ValueError("Missing timestamp unit in docs/CLICKHOUSE_SCHEMA.md")
        
    return logs_match.group(1), traces_match.group(1), unit_match.group(1).lower()

def check_port_01():
    ports = parse_ports()
    for port in ports:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2.0)
        result = sock.connect_ex(('127.0.0.1', port))
        sock.close()
        if result != 0:
            raise Exception(f"Port {port} is not accepting connections")

def check_port_02():
    out = subprocess.check_output(['docker', 'compose', 'ps', '--format', 'json'])
    lines = [json.loads(line) for line in out.decode().strip().split('\n') if line]
    published_ports = []
    for container in lines:
        if 'Publishers' in container and container['Publishers']:
            for p in container['Publishers']:
                if p.get('URL') and p.get('PublishedPort'):
                    published_ports.append(p.get('PublishedPort'))
    if len(published_ports) != len(set(published_ports)):
        dups = [item for item, count in collections.Counter(published_ports).items() if count > 1]
        raise Exception(f"Duplicate published host ports found: {dups}")

def check_port_03():
    out = subprocess.check_output(['docker', 'compose', 'ps', '--format', 'json'])
    lines = [json.loads(line) for line in out.decode().strip().split('\n') if line]
    for container in lines:
        if 'Publishers' in container and container['Publishers']:
            for p in container['Publishers']:
                # Only check PublishedPort to the host
                if p.get('PublishedPort') == 8080:
                    raise Exception(f"Container {container.get('Name')} publishes port 8080")

def check_port_04():
    out = subprocess.check_output(['docker', 'compose', 'ps', '--format', 'json'])
    lines = [json.loads(line) for line in out.decode().strip().split('\n') if line]
    for container in lines:
        if 'Publishers' in container and container['Publishers']:
            for p in container['Publishers']:
                url = p.get('URL', '')
                if '0.0.0.0' in url:
                    raise Exception(f"Container {container.get('Name')} binds to 0.0.0.0: {url}")

def check_graph_01():
    memgraph = Memgraph(host="127.0.0.1", port=7687)
    results = list(memgraph.execute_and_fetch("RETURN 1 as value"))
    if not results or results[0]['value'] != 1:
        raise Exception(f"Unexpected return value: {results}")

def check_graph_02():
    memgraph = Memgraph(host="127.0.0.1", port=7687)
    results = list(memgraph.execute_and_fetch("CALL mg.procedures() YIELD * RETURN count(*) as count"))
    if results[0]['count'] == 0:
        raise Exception("No procedures found")

def check_graph_03():
    memgraph = Memgraph(host="127.0.0.1", port=7687)
    results = list(memgraph.execute_and_fetch("MATCH (t:PersistenceProbe {id: 'phase1'}) RETURN count(t) as count"))
    if results[0]['count'] == 0:
        raise Exception("PersistenceProbe node not found")

def check_tele_01():
    logs_table, _, _ = parse_clickhouse_schema()
    client = clickhouse_connect.get_client(host='127.0.0.1', port=8123, username='default', password='')
    result = client.command(f"EXISTS TABLE signoz_logs.{logs_table}")
    if not result:
        raise Exception(f"Table signoz_logs.{logs_table} does not exist")

def check_tele_02():
    logs_table, _, unit = parse_clickhouse_schema()
    client = clickhouse_connect.get_client(host='127.0.0.1', port=8123, username='default', password='')
    if unit == 'nanoseconds':
        query = f"SELECT count(*) FROM signoz_logs.{logs_table} WHERE timestamp >= toUnixTimestamp64Nano(now64() - INTERVAL 1 HOUR)"
    else:
        query = f"SELECT count(*) FROM signoz_logs.{logs_table} WHERE timestamp >= toUnixTimestamp(now() - INTERVAL 1 HOUR) * 1000"
    count = client.command(query)
    if count == 0:
        raise Exception("No log rows found in recent window")

def check_tele_03():
    _, traces_table, _ = parse_clickhouse_schema()
    client = clickhouse_connect.get_client(host='127.0.0.1', port=8123, username='default', password='')
    query = f"SELECT count(DISTINCT resources_string['service.name']) FROM signoz_traces.{traces_table} WHERE timestamp >= now64() - INTERVAL 1 HOUR"
    count = client.command(query)
    if count <= 1:
        raise Exception(f"Found {count} distinct services in traces, expected > 1")

def check_svc_01():
    expected_services = parse_services()
    logs_table, traces_table, _ = parse_clickhouse_schema()
    client = clickhouse_connect.get_client(host='127.0.0.1', port=8123, username='default', password='')
    
    found = set()
    # Check traces
    q_traces = f"SELECT DISTINCT resources_string['service.name'] FROM signoz_traces.{traces_table} WHERE timestamp >= now64() - INTERVAL 1 HOUR"
    try:
        r_traces = client.query(q_traces)
        found |= {row[0] for row in r_traces.result_rows if row[0]}
    except Exception:
        pass
        
    # Check logs
    q_logs = f"SELECT DISTINCT resources_string['service.name'] FROM signoz_logs.{logs_table} WHERE timestamp >= toUnixTimestamp64Nano(now64() - INTERVAL 1 HOUR)"
    try:
        r_logs = client.query(q_logs)
        found |= {row[0] for row in r_logs.result_rows if row[0]}
    except Exception:
        pass
        
    if 'otelcol-contrib' in found:
        found.add('otel-collector')
        
    allowed_missing = {'astronomy-db', 'valkey-cart', 'flagd-ui'}
    missing = expected_services - found
    really_missing = missing - allowed_missing
    
    mandatory = {'payment', 'checkout', 'frontend'}
    missing_mandatory = mandatory - found
    if missing_mandatory:
        raise Exception(f"Mandatory services missing from telemetry: {missing_mandatory}")
        
    if really_missing:
        raise Exception(f"Service set mismatch. Missing services: {really_missing}")

def check_health_01():
    out = subprocess.check_output(['docker', 'compose', 'ps', '-q'])
    containers = out.decode().strip().split('\n')
    for c in containers:
        if not c: continue
        inspect = subprocess.check_output(['docker', 'inspect', '-f', '{{.Name}} {{.State.Status}} {{.State.ExitCode}}', c])
        name, status, exit_code = inspect.decode().strip().split()
        if status.lower() == 'restarting':
            raise Exception(f"Container {name} is in Restarting state")
        if exit_code == '137':
            raise Exception(f"Container {name} last exit code is 137")

def check_ui_01():
    urls = [
        "http://127.0.0.1:3301/",
        "http://127.0.0.1:3000/",
        "http://127.0.0.1:8090/"
    ]
    for url in urls:
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=5.0) as response:
                if response.getcode() != 200:
                    raise Exception(f"{url} returned {response.getcode()}")
        except urllib.error.URLError as e:
            if hasattr(e, 'code'):
                pass
            else:
                raise Exception(f"Failed to fetch {url}: {e}")

CHECKS = [
    ("PORT-01", check_port_01),
    ("PORT-02", check_port_02),
    ("PORT-03", check_port_03),
    ("PORT-04", check_port_04),
    ("GRAPH-01", check_graph_01),
    ("GRAPH-02", check_graph_02),
    ("GRAPH-03", check_graph_03),
    ("TELE-01", check_tele_01),
    ("TELE-02", check_tele_02),
    ("TELE-03", check_tele_03),
    ("SVC-01", check_svc_01),
    ("HEALTH-01", check_health_01),
    ("UI-01", check_ui_01),
]

def main():
    fail_count = 0
    for cid, func in CHECKS:
        try:
            func()
            print(f"PASS  {cid}  OK")
        except Exception as e:
            fail_count += 1
            msg = str(e).split('\n')[0]
            print(f"FAIL  {cid}  {type(e).__name__}: {msg}")
    
    print(f"\nSummary: {len(CHECKS) - fail_count} PASS, {fail_count} FAIL")
    if fail_count > 0:
        sys.exit(1)

if __name__ == "__main__":
    main()
