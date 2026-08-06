from typing import Dict, Type
from src.production.topology.plugin import TopologyPlugin

# Explicit dictionary mapping for internal plugin registry
PLUGINS: Dict[str, Type] = {}


class TopologyManager:
    """Manager and registry for topology plugins."""
    
    @classmethod
    def get_plugin_class(cls, name: str) -> Type[TopologyPlugin]:
        """
        Retrieve a plugin class by name from the registry.
        
        Args:
            name: The name of the plugin to retrieve.
            
        Returns:
            The plugin class.
            
        Raises:
            ValueError: If the plugin is not found in the registry.
            TypeError: If the retrieved plugin does not subclass TopologyPlugin.
        """
        if name not in PLUGINS:
            raise ValueError(f"Plugin '{name}' not found in registry.")
            
        plugin_class = PLUGINS[name]
        
        if not issubclass(plugin_class, TopologyPlugin):
            raise TypeError(f"Plugin '{name}' does not subclass TopologyPlugin.")
            
        return plugin_class

    @classmethod
    def register_plugin(cls, name: str, plugin_class: Type):
        """
        Register a plugin class.
        
        Args:
            name: The name of the plugin to register.
            plugin_class: The plugin class to register.
        """
        PLUGINS[name] = plugin_class
