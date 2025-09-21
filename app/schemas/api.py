from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.models.registry import EntryType


class AgentSearchResult(BaseModel):
    """Response model for agent search results."""

    agent_id: str
    agent_name: str
    facts_url: str
    resolver_url: Optional[str]
    tags: List[str]
    match_score: float = Field(description="Relevance score for search query")


class AgentResolutionResult(BaseModel):
    """Response model for agent resolution."""

    agent_name: str
    facts_url: str
    resolver_url: Optional[str]
    ttl: int
    type: EntryType
    namespace: Optional[str] = Field(None, description="If federated, the namespace")


class AdminAgentRequest(BaseModel):
    """Request model for adding/updating agents via admin API."""

    agent_id: str
    agent_name: str
    facts_url: str
    private_facts_url: Optional[str] = None
    resolver_url: Optional[str] = None
    tags: List[str]
    ttl: int = 3600
    signature: str
    publisher: str


class AdminNamespaceRequest(BaseModel):
    """Request model for adding/updating namespaces via admin API."""

    namespace: str
    sub_index_url: str
    registry_id: Optional[str] = None
    ttl: int = 7200
    signature: str


class RevokeRequest(BaseModel):
    """Request model for revoking agents."""

    agent_id: str
    reason: Optional[str] = None


class PaginatedAgentsResponse(BaseModel):
    """Response model for paginated agents list."""

    agents: List[Dict[str, object]]
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
                        "last_updated": "2025-09-11T12:00:00Z",
                    }
                ],
                "total_count": 150,
                "limit": 50,
                "offset": 0,
                "has_next": True,
            }
        }


class SearchResponse(BaseModel):
    """Response model for search endpoint."""

    query: str
    results: List[AgentSearchResult]
    total_count: int


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    timestamp: datetime
    database: Dict[str, object]
    version: str = "1.0.0"
