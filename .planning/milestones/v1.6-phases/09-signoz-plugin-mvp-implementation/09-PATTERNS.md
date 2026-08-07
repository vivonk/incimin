# Phase 09: SigNoz Plugin MVP Implementation - Patterns

## Files to be Created/Modified

### 1. `src/production/topology/plugins/signoz.py` (Created)
**Role:** Implements the SigNoz-specific plugin for fetching and parsing topology data from the SigNoz API.
**Data Flow:**
1. Calls SigNoz API endpoints using `httpx` with exponential backoff (via `tenacity`).
2. Parses incoming JSON responses (ignoring malformed entities rather than failing the generator).
3. Normalizes payloads into `ServiceNode` and `ServiceEdge` Pydantic models.
4. Yields these models through the `fetch_topology` async generator back to the caller.

**Closest Existing Analogs:** 
- `src/production/topology/plugin.py` (Core Abstraction)
- `src/production/topology/models.py` (Data Models)

**Extracted Code Excerpts:**
*From `src/production/topology/plugin.py`:*
```python
from abc import ABC, abstractmethod
from typing import AsyncIterator
from pydantic_settings import BaseSettings

from src.production.topology.models import ServiceNode, ServiceEdge


class PluginConfig(BaseSettings):
    """Base configuration model for topology plugins."""
    pass


class TopologyPlugin(ABC):
    """Core abstraction layer for topology plugins."""
    
    def __init__(self, config: PluginConfig):
        self.config = config
        
    @abstractmethod
    async def fetch_topology(self) -> AsyncIterator[ServiceNode | ServiceEdge]:
        """
        Fetch topology data.
        
        Yields:
            ServiceNode or ServiceEdge objects.
        """
        yield # type: ignore
```

*From `src/production/topology/models.py`:*
```python
class EntityMetadataMixin(BaseModel):
    source: str
    external_id: str
    fetched_at: str = Field(default_factory=lambda: datetime.datetime.now().isoformat())
    schema_version: str

class ServiceNode(EntityMetadataMixin):
    name: str = "unknown"
    type: str = "service"
    attributes: Dict[str, Any] = Field(default_factory=dict)
```


### 2. `pyproject.toml` (Modified)
**Role:** Project configuration file.
**Data Flow:** Package resolution during installation.

**Closest Existing Analog:** Existing `[project]` block defining standard dependencies.

**Extracted Code Excerpts:**
*From `pyproject.toml`:*
```toml
[project]
name = "incimin"
version = "0.1.0"
requires-python = ">=3.12,<3.13"
dependencies = [
    # ... existing dependencies ...
]
```
*(Need to add `httpx` and `tenacity` to this list)*
