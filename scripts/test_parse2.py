import re
from pathlib import Path

def parse_clickhouse_schema():
    content = Path('docs/CLICKHOUSE_SCHEMA.md').read_text()
    
    logs_table = None
    traces_table = None
    
    logs_match = re.search(r'Logs table.*`signoz_logs\.([a-zA-Z0-9_]+)`', content)
    if logs_match:
        logs_table = logs_match.group(1)
        
    traces_match = re.search(r'Traces table.*`signoz_traces\.([a-zA-Z0-9_]+)`', content)
    if traces_match:
        traces_table = traces_match.group(1)
        
    unit_match = re.search(r'Timestamp unit for logs.*?\|.*?\*\*(nanoseconds|milliseconds)\*\*', content, re.IGNORECASE)
    unit = unit_match.group(1).lower() if unit_match else None
        
    if not logs_table:
        raise ValueError("Missing logs table name in docs/CLICKHOUSE_SCHEMA.md")
    if not traces_table:
        raise ValueError("Missing traces table name in docs/CLICKHOUSE_SCHEMA.md")
    if not unit:
        raise ValueError("Missing timestamp unit in docs/CLICKHOUSE_SCHEMA.md")
        
    return logs_table, traces_table, unit

print(parse_clickhouse_schema())
