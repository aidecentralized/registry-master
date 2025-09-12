"""
Global Registry Master - Registry Service API
FastAPI application providing REST endpoints for agent registry
"""

import os
import logging
from typing import List, Optional
from datetime import datetime
from fastapi import FastAPI, HTTPException, Depends, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from database import RegistryDatabase
from models import (
    DirectAgentEntry, FederatedNamespaceEntry, 
    AgentSearchResult, AgentResolutionResult, StructuredSearchQuery, EntryType
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Global Registry Master",
    description="API for agent discovery and resolution",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
security = HTTPBearer(auto_error=False)

# Global database instance
db = RegistryDatabase()


# Request/Response Models
class SearchResponse(BaseModel):
    """Response model for search endpoint"""
    query: str
    results: List[AgentSearchResult]
    total_count: int


class AdminAgentRequest(BaseModel):
    """Request model for adding/updating agents via admin API"""
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
    """Request model for adding/updating namespaces via admin API"""
    namespace: str
    sub_index_url: str
    registry_id: Optional[str] = None
    ttl: int = 7200
    signature: str


class RevokeRequest(BaseModel):
    """Request model for revoking agents"""
    agent_id: str
    reason: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    timestamp: datetime
    database: dict
    version: str = "1.0.0"


# Dependency functions
async def get_database():
    """Dependency to get database instance"""
    if not db._client:
        if not db.connect():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database connection failed"
            )
    return db


async def verify_admin_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify admin authentication for write operations"""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required for admin operations"
        )
    
    # In production, implement proper JWT validation
    admin_token = os.getenv('ADMIN_TOKEN', 'admin-secret-token')
    if credentials.credentials != admin_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid admin token"
        )
    
    return credentials


# Startup and shutdown events
@app.on_event("startup")
async def startup_event():
    """Initialize database connection on startup"""
    if not db.connect():
        logger.error("Failed to connect to database during startup")
        raise RuntimeError("Database connection failed")
    logger.info("Registry service started successfully")


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up database connection on shutdown"""
    db.disconnect()
    logger.info("Registry service shutdown complete")


# Public API Endpoints

@app.get("/healthz", response_model=HealthResponse)
async def health_check(db_instance: RegistryDatabase = Depends(get_database)):
    """Health check endpoint for monitoring and load balancer"""
    db_health = db_instance.get_health_status()
    
    return HealthResponse(
        status="healthy" if db_health["connected"] else "unhealthy",
        timestamp=datetime.utcnow(),
        database=db_health
    )


@app.get("/v1/index/search", response_model=SearchResponse)
async def search_agents(
    searchparam: str = Query(..., description="JSON object with search key-value pairs, e.g. '{\"agent_name\":\"urn:\"}' or '{\"agent_id\":\"1111\"}' or '{\"tags\":\"tax\"}'"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of results"),
    db_instance: RegistryDatabase = Depends(get_database)
):
    """Search for agents using structured key-value parameters in JSON format"""
    try:
        # Parse the JSON search parameters
        import json
        try:
            search_dict = json.loads(searchparam)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JSON in searchparam. Example: '{\"name\":\"urn:\"}'"
            )
        
        if not isinstance(search_dict, dict) or not search_dict:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="searchparam must be a non-empty JSON object with key-value pairs"
            )
        
        # Validate that keys match MongoDB fields
        valid_keys = {"agent_name", "agent_id", "tags", "publisher"}
        invalid_keys = set(search_dict.keys()) - valid_keys
        if invalid_keys:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid search keys: {list(invalid_keys)}. Valid keys are: {list(valid_keys)}"
            )
        
        results = db_instance.structured_search(search_dict, limit)
        
        search_results = [
            AgentSearchResult(
                agent_id=result["agent_id"],
                agent_name=result["agent_name"],
                facts_url=result["facts_url"],
                resolver_url=result.get("resolver_url"),
                tags=result["tags"],
                match_score=result.get("match_score", 1.0)
            )
            for result in results
        ]
        
        return SearchResponse(
            query=str(search_dict),
            results=search_results,
            total_count=len(search_results)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Search operation failed"
        )

@app.get("/v1/agents/resolve", response_model=AgentResolutionResult)
async def resolve_agent(
    agent_name: str = Query(..., description="Agent URN to resolve"),
    db_instance: RegistryDatabase = Depends(get_database)
):
    """Resolve agent URN to get address information"""
    try:
        result = db_instance.resolve_agent(agent_name)
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent not found: {agent_name}"
            )
        
        return AgentResolutionResult(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Resolution failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Resolution operation failed"
        )


# Admin API Endpoints (require authentication)

@app.post("/v1/admin/agent", status_code=status.HTTP_201_CREATED)
async def add_agent(
    request: AdminAgentRequest,
    db_instance: RegistryDatabase = Depends(get_database),
    _: HTTPAuthorizationCredentials = Depends(verify_admin_token)
):
    """Add or update a direct agent entry"""
    try:
        agent_entry = DirectAgentEntry(
            id=f"agent:{request.agent_id}",
            agent_id=request.agent_id,
            agent_name=request.agent_name,
            facts_url=request.facts_url,
            private_facts_url=request.private_facts_url,
            resolver_url=request.resolver_url,
            tags=request.tags,
            ttl=request.ttl,
            signature=request.signature,
            publisher=request.publisher,
            created_at=datetime.utcnow(),
            last_updated=datetime.utcnow()
        )
        
        success = db_instance.insert_direct_agent(agent_entry)
        
        if not success:
            # Try updating existing entry
            updates = {
                "agent_name": request.agent_name,
                "facts_url": request.facts_url,
                "private_facts_url": request.private_facts_url,
                "resolver_url": request.resolver_url,
                "tags": request.tags,
                "ttl": request.ttl,
                "signature": request.signature,
                "publisher": request.publisher
            }
            
            update_success = db_instance.update_agent(request.agent_id, updates)
            if not update_success:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Failed to add or update agent"
                )
        
        return {"message": f"Agent {request.agent_id} added/updated successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add agent: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add agent"
        )


@app.post("/v1/admin/namespace", status_code=status.HTTP_201_CREATED)
async def add_namespace(
    request: AdminNamespaceRequest,
    db_instance: RegistryDatabase = Depends(get_database),
    _: HTTPAuthorizationCredentials = Depends(verify_admin_token)
):
    """Add or update a federated namespace entry"""
    try:
        namespace_entry = FederatedNamespaceEntry(
            id=f"ns:{request.namespace}",
            namespace=request.namespace,
            sub_index_url=request.sub_index_url,
            registry_id=request.registry_id,
            ttl=request.ttl,
            signature=request.signature,
            created_at=datetime.utcnow(),
            last_updated=datetime.utcnow()
        )
        
        success = db_instance.insert_federated_namespace(namespace_entry)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Namespace {request.namespace} already exists"
            )
        
        return {"message": f"Namespace {request.namespace} added successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add namespace: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add namespace"
        )


@app.post("/v1/admin/revoke", status_code=status.HTTP_200_OK)
async def revoke_agent(
    request: RevokeRequest,
    db_instance: RegistryDatabase = Depends(get_database),
    _: HTTPAuthorizationCredentials = Depends(verify_admin_token)
):
    """Revoke an agent from the registry"""
    try:
        success = db_instance.revoke_agent(request.agent_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent not found: {request.agent_id}"
            )
        
        return {"message": f"Agent {request.agent_id} revoked successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to revoke agent: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to revoke agent"
        )


# Additional utility endpoints

@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "service": "Global Registry Master",
        "version": "1.0.0",
        "endpoints": {
            "health": "/healthz",
            "search": "/v1/index/search",
            "resolve": "/v1/agents/resolve",
            "docs": "/docs"
        }
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)