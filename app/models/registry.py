from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class EntryType(str, Enum):
    DIRECT = "direct"
    FEDERATED = "federated"


class DirectAgentEntry(BaseModel):
    """Schema for direct agent entries in the registry"""
    id: str = Field(..., alias="_id", description="Unique Mongo ID with 'agent:' prefix")
    type: EntryType = Field(EntryType.DIRECT, description="Entry type")
    agent_id: str = Field(..., description="Unique agent identifier")
    agent_name: str = Field(..., description="Human-readable URN")
    facts_url: str = Field(..., description="URL to agent facts")
    private_facts_url: Optional[str] = Field(None, description="Optional private facts URL")
    resolver_url: Optional[str] = Field(None, description="Optional resolver URL")
    tags: List[str] = Field(..., description="Capability tags for exact match")
    ttl: int = Field(..., description="Cache lifetime in seconds")
    signature: str = Field(..., description="ed25519 signature by publisher")
    publisher: str = Field(..., description="Who published this entry")
    created_at: datetime = Field(..., description="Creation timestamp")
    last_updated: datetime = Field(..., description="Last update timestamp")

    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class FederatedNamespaceEntry(BaseModel):
    """Schema for federated namespace entries in the registry"""
    id: str = Field(..., alias="_id", description="Unique Mongo ID with 'ns:' prefix")
    type: EntryType = Field(EntryType.FEDERATED, description="Entry type")
    namespace: str = Field(..., description="Delegated namespace")
    sub_index_url: str = Field(..., description="Authoritative sub-index URL")
    registry_id: Optional[str] = Field(None, description="Optional region/infra ID")
    ttl: int = Field(..., description="Cache lifetime for this pointer")
    signature: str = Field(..., description="ed25519 signature by Registry Master")
    created_at: datetime = Field(..., description="Creation timestamp")
    last_updated: datetime = Field(..., description="Last update timestamp")

    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
