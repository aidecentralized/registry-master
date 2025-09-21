import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_repository
from app.db.repository import RegistryRepository
from app.models.registry import EntryType
from app.schemas.api import (
    AgentResolutionResult,
    AgentSearchResult,
    HealthResponse,
    PaginatedAgentsResponse,
    SearchResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/healthz", response_model=HealthResponse)
async def health_check(repository: RegistryRepository = Depends(get_repository)) -> HealthResponse:
    """Health check endpoint for monitoring and load balancer."""
    db_health = repository.get_health_status()

    return HealthResponse(
        status="healthy" if db_health.get("connected") else "unhealthy",
        timestamp=datetime.utcnow(),
        database=db_health,
    )


@router.get("/v1/index/search", response_model=SearchResponse)
async def search_agents(
    searchparam: str = Query(
        ...,
        description='JSON object with search key-value pairs, e.g. "{\"agent_name\":\"urn:\"}"',
    ),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of results"),
    repository: RegistryRepository = Depends(get_repository),
) -> SearchResponse:
    """Search for agents using structured key-value parameters in JSON format."""
    try:
        try:
            search_dict = json.loads(searchparam)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JSON in searchparam. Example: '{\"name\":\"urn:\"}'",
            ) from exc

        if not isinstance(search_dict, dict) or not search_dict:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="searchparam must be a non-empty JSON object with key-value pairs",
            )

        valid_keys = {"agent_name", "agent_id", "tags", "publisher"}
        invalid_keys = set(search_dict.keys()) - valid_keys
        if invalid_keys:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid search keys: {list(invalid_keys)}. Valid keys are: {list(valid_keys)}",
            )

        results = repository.structured_search(search_dict, limit)

        search_results = [
            AgentSearchResult(
                agent_id=result["agent_id"],
                agent_name=result["agent_name"],
                facts_url=result["facts_url"],
                resolver_url=result.get("resolver_url"),
                tags=result["tags"],
                match_score=result.get("match_score", 1.0),
            )
            for result in results
        ]

        return SearchResponse(
            query=str(search_dict),
            results=search_results,
            total_count=len(search_results),
        )
    except HTTPException:
        raise
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Search failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Search operation failed",
        ) from exc


@router.get("/v1/agents/resolve", response_model=AgentResolutionResult)
async def resolve_agent(
    agent_name: str = Query(..., description="Agent URN to resolve"),
    repository: RegistryRepository = Depends(get_repository),
) -> AgentResolutionResult:
    """Resolve agent URN to get address information."""
    try:
        result = repository.resolve_agent(agent_name)

        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent not found: {agent_name}",
            )

        return AgentResolutionResult(**result)
    except HTTPException:
        raise
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Resolution failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Resolution operation failed",
        ) from exc


@router.get("/v1/agents/list", response_model=PaginatedAgentsResponse)
async def list_agents(
    type_: Optional[str] = Query(
        None,
        alias="type",
        description="Filter by entry type: 'direct', 'federated', or 'all'",
    ),
    limit: int = Query(50, ge=1, le=500, description="Maximum number of agents per page"),
    offset: int = Query(0, ge=0, description="Number of agents to skip for pagination"),
    repository: RegistryRepository = Depends(get_repository),
) -> PaginatedAgentsResponse:
    """List all agents with pagination support."""
    try:
        if type_ and type_ not in [EntryType.DIRECT.value, EntryType.FEDERATED.value, "all"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid type parameter. Must be 'direct', 'federated', or 'all'",
            )

        result = repository.get_all_agents(entry_type=type_, limit=limit, offset=offset)

        if "error" in result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to retrieve agents: {result['error']}",
            )

        return PaginatedAgentsResponse(**result)
    except HTTPException:
        raise
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("List agents failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list agents",
        ) from exc


@router.get("/")
async def root() -> dict:
    """Root endpoint with API information."""
    return {
        "service": "Global Registry Master",
        "version": "1.0.0",
        "endpoints": {
            "health": "/healthz",
            "search": "/v1/index/search",
            "resolve": "/v1/agents/resolve",
            "list": "/v1/agents/list",
            "docs": "/docs",
        },
    }
