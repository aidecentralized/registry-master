import logging
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, get_settings
from app.db.repository import RegistryRepository

logger = logging.getLogger(__name__)

_security = HTTPBearer(auto_error=False)
_repository: Optional[RegistryRepository] = None


def init_repository(settings: Optional[Settings] = None) -> RegistryRepository:
    """Initialise and connect the shared repository instance."""
    global _repository

    settings = settings or get_settings()

    if _repository is None:
        _repository = RegistryRepository(settings)

    if not _repository.is_connected() and not _repository.connect():
        raise RuntimeError("Database connection failed")

    return _repository


def shutdown_repository() -> None:
    """Tear down the shared repository instance."""
    global _repository

    if _repository and _repository.is_connected():
        _repository.disconnect()

    _repository = None


def get_repository(settings: Settings = Depends(get_settings)) -> RegistryRepository:
    """Provide a connected MongoDB repository instance."""
    global _repository
    try:
        return init_repository(settings)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection failed",
        ) from exc


def verify_admin_token(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
    settings: Settings = Depends(get_settings),
) -> HTTPAuthorizationCredentials:
    """Validate admin token provided for privileged operations."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required for admin operations",
        )

    if credentials.credentials != settings.admin_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid admin token",
        )

    return credentials
