import re

def parse_ports():
    with open('docs/PORTS.md', 'r') as f:
        content = f.read()
    ports = []
    for match in re.finditer(r'\|\s*(\d+)\s*\|\s*127\.0\.0\.1\s*\|', content):
        ports.append(int(match.group(1)))
    return ports

def parse_services():
    with open('docs/OTEL_DEMO_SERVICES.md', 'r') as f:
        content = f.read()
    services = []
    for match in re.finditer(r'(?m)^\d+\.\s+([a-zA-Z0-9-]+)', content):
        services.append(match.group(1))
    return services

def parse_tables():
    with open('docs/CLICKHOUSE_SCHEMA.md', 'r') as f:
        content = f.read()
    logs = re.search(r'Logs table.*`signoz_logs\.(distributed_logs_v2)`', content)
    traces = re.search(r'Traces table.*`signoz_traces\.(distributed_signoz_index_v3)`', content)
    return logs.group(1) if logs else None, traces.group(1) if traces else None

print("Ports:", parse_ports())
print("Services:", parse_services())
print("Tables:", parse_tables())
