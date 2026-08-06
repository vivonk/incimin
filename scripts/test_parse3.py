import re
from pathlib import Path

def parse_ports():
    content = Path('docs/PORTS.md').read_text()
    ports = []
    for line in content.splitlines():
        if line.startswith('|') and '127.0.0.1' in line:
            parts = [p.strip() for p in line.split('|')]
            if len(parts) > 2 and parts[1].isdigit():
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

print("Ports:", parse_ports())
print("Services:", parse_services())
print("Services count:", len(parse_services()))
