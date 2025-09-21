from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials

from app.api.dependencies import get_repository, verify_admin_token
from app.db.repository import RegistryRepository
from app.models.registry import DirectAgentEntry, FederatedNamespaceEntry
from app.schemas.api import AdminAgentRequest, AdminNamespaceRequest, RevokeRequest

router = APIRouter()


@router.post("/v1/admin/agent", status_code=status.HTTP_201_CREATED)
async def add_agent(
    request: AdminAgentRequest,
    repository: RegistryRepository = Depends(get_repository),
    _: HTTPAuthorizationCredentials = Depends(verify_admin_token),
) -> dict:
    """Add or update a direct agent entry."""
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
            last_updated=datetime.utcnow(),
        )

        success = repository.insert_direct_agent(agent_entry)

        if not success:
            updates = {
                "agent_name": request.agent_name,
                "facts_url": request.facts_url,
                "private_facts_url": request.private_facts_url,
                "resolver_url": request.resolver_url,
                "tags": request.tags,
                "ttl": request.ttl,
                "signature": request.signature,
                "publisher": request.publisher,
            }

            update_success = repository.update_agent(request.agent_id, updates)
            if not update_success:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Failed to add or update agent",
                )

        return {"message": f"Agent {request.agent_id} added/updated successfully"}
    except HTTPException:
        raise
    except Exception as exc:  # pylint: disable=broad-except
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add agent",
        ) from exc


@router.post("/v1/admin/namespace", status_code=status.HTTP_201_CREATED)
async def add_namespace(
    request: AdminNamespaceRequest,
    repository: RegistryRepository = Depends(get_repository),
    _: HTTPAuthorizationCredentials = Depends(verify_admin_token),
) -> dict:
    """Add or update a federated namespace entry."""
    try:
        namespace_entry = FederatedNamespaceEntry(
            id=f"ns:{request.namespace}",
            namespace=request.namespace,
            sub_index_url=request.sub_index_url,
            registry_id=request.registry_id,
            ttl=request.ttl,
            signature=request.signature,
            created_at=datetime.utcnow(),
            last_updated=datetime.utcnow(),
        )

        success = repository.insert_federated_namespace(namespace_entry)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Namespace {request.namespace} already exists",
            )

        return {"message": f"Namespace {request.namespace} added successfully"}
    except HTTPException:
        raise
    except Exception as exc:  # pylint: disable=broad-except
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add namespace",
        ) from exc


@router.post("/v1/admin/revoke", status_code=status.HTTP_200_OK)
async def revoke_agent(
    request: RevokeRequest,
    repository: RegistryRepository = Depends(get_repository),
    _: HTTPAuthorizationCredentials = Depends(verify_admin_token),
) -> dict:
    """Revoke an agent from the registry."""
    try:
        success = repository.revoke_agent(request.agent_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent not found: {request.agent_id}",
            )

        return {"message": f"Agent {request.agent_id} revoked successfully"}
    except HTTPException:
        raise
    except Exception as exc:  # pylint: disable=broad-except
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to revoke agent",
        ) from exc
