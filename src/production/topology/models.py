import uuid
import datetime
from pydantic import BaseModel, Field, model_validator
from typing import Optional, Dict, Any

NAMESPACE_TOPOLOGY = uuid.UUID('f05d5483-e18e-4a6c-9ba3-81b212f71946')

class EntityMetadataMixin(BaseModel):
    source: str
    external_id: str
    fetched_at: str = Field(default_factory=lambda: datetime.datetime.now().isoformat())
    schema_version: str
    
    @property
    def internal_id(self) -> str:
        return str(uuid.uuid5(NAMESPACE_TOPOLOGY, f"{self.source}:{self.external_id}"))

class ServiceNode(EntityMetadataMixin):
    name: str = "unknown"
    type: str = "service"
    attributes: Dict[str, Any] = Field(default_factory=dict)
    
    @model_validator(mode='before')
    @classmethod
    def set_defaults(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "name" not in data or not data["name"]:
                data["name"] = "unknown"
        return data

class ServiceEdge(EntityMetadataMixin):
    source_node_id: str
    target_node_id: str
    type: str = "calls"
    attributes: Dict[str, Any] = Field(default_factory=dict)
