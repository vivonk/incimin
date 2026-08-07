import pytest
from typing import AsyncIterator
from pydantic_settings import BaseSettings

from src.production.topology.plugin import TopologyPlugin, PluginConfig
from src.production.topology.manager import TopologyManager, PLUGINS
from src.production.topology.models import ServiceNode, ServiceEdge


def test_topology_plugin_is_abstract():
    """Verify that TopologyPlugin cannot be instantiated without implementing fetch_topology."""
    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        TopologyPlugin(PluginConfig())


def test_topology_plugin_instantiation():
    """Verify that a subclass implementing fetch_topology can be instantiated."""
    class ValidPlugin(TopologyPlugin):
        async def fetch_topology(self) -> AsyncIterator[ServiceNode | ServiceEdge]:
            yield ServiceNode(source="test", external_id="1", schema_version="1")
            
    plugin = ValidPlugin(PluginConfig())
    assert isinstance(plugin, TopologyPlugin)


def test_topology_manager_registration_and_retrieval():
    """Verify that a valid plugin can be registered and retrieved."""
    class ValidPlugin(TopologyPlugin):
        async def fetch_topology(self) -> AsyncIterator[ServiceNode | ServiceEdge]:
            yield ServiceNode(source="test", external_id="1", schema_version="1")
            
    # Manually register the plugin in the registry mapping
    PLUGINS["valid_plugin"] = ValidPlugin
    
    plugin_class = TopologyManager.get_plugin_class("valid_plugin")
    assert plugin_class is ValidPlugin


def test_topology_manager_invalid_plugin():
    """Verify that an invalid plugin raises a TypeError upon retrieval."""
    class InvalidPlugin:
        pass
        
    PLUGINS["invalid_plugin"] = InvalidPlugin
    
    with pytest.raises(TypeError, match="does not subclass TopologyPlugin"):
        TopologyManager.get_plugin_class("invalid_plugin")


def test_topology_manager_missing_plugin():
    """Verify that retrieving a missing plugin raises a ValueError."""
    with pytest.raises(ValueError, match="not found in registry"):
        TopologyManager.get_plugin_class("nonexistent_plugin")
