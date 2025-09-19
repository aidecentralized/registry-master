from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


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


class AgentSearchResult(BaseModel):
    """Response model for agent search results"""
    agent_id: str
    agent_name: str
    facts_url: str
    resolver_url: Optional[str]
    tags: List[str]
    match_score: float = Field(description="Relevance score for search query")


class AgentResolutionResult(BaseModel):
    """Response model for agent resolution"""
    agent_name: str
    facts_url: str
    resolver_url: Optional[str]
    ttl: int
    type: EntryType
    namespace: Optional[str] = Field(None, description="If federated, the namespace")


class StructuredSearchQuery(BaseModel):
    """Request model for structured search queries"""
    name: Optional[str] = Field(None, description="Search by agent_name (supports partial matching)")
    agent_id: Optional[str] = Field(None, alias="agent-id", description="Search by agent_id")
    tags: Optional[str] = Field(None, description="Search by capability tags")
    publisher: Optional[str] = Field(None, description="Search by publisher")
    
    class Config:
        populate_by_name = True


class PaginatedAgentsResponse(BaseModel):
    """Response model for paginated agents list"""
    agents: List[Dict[str, Any]]
    total_count: int = Field(description="Total number of agents matching criteria")
    limit: int = Field(description="Maximum items per page")
    offset: int = Field(description="Current page offset")
    has_next: bool = Field(description="Whether more pages are available")
    
    class Config:
        schema_extra = {
            "example": {
                "agents": [
                    {
                        "type": "direct",
                        "agent_id": "nanda:uuid-1111",
                        "agent_name": "urn:agent:nanda:TaxBot",
                        "facts_url": "https://nanda.com/.well-known/agent-facts/1111",
                        "resolver_url": "https://resolver.nanda.com/dispatch",
                        "tags": ["tax.calculate", "finance.reports"],
                        "publisher": "nanda",
                        "ttl": 3600,
                        "created_at": "2025-09-11T12:00:00Z",
                        "last_updated": "2025-09-11T12:00:00Z"
                    }
                ],
                "total_count": 150,
                "limit": 50,
                "offset": 0,
                "has_next": True
            }
        }