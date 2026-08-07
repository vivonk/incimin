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
