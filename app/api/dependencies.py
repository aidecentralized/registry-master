import logging
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, get_settings
from app.db.repository import RegistryRepository
from app.services.kafka_service import KafkaService
from app.services.change_stream_monitor import ChangeStreamMonitor

logger = logging.getLogger(__name__)

_security = HTTPBearer(auto_error=False)
_repository: Optional[RegistryRepository] = None
_kafka_service: Optional[KafkaService] = None
_change_stream_monitor: Optional[ChangeStreamMonitor] = None


def init_repository(settings: Optional[Settings] = None) -> RegistryRepository:
    """Initialise and connect the shared repository instance."""
    global _repository

    settings = settings or get_settings()

    if _repository is None:
        _repository = RegistryRepository(settings)

    if not _repository.is_connected() and not _repository.connect():
        raise RuntimeError("Database connection failed")

    return _repository


def init_kafka_services(settings: Optional[Settings] = None) -> None:
    """Initialize Kafka services and change stream monitoring."""
    global _kafka_service, _change_stream_monitor
    
    settings = settings or get_settings()
    
    if not settings.kafka_enabled:
        logger.info("Kafka integration disabled")
        return
    
    # Initialize Kafka service
    if _kafka_service is None:
        _kafka_service = KafkaService(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            topic=settings.kafka_topic
        )
        
        if _kafka_service.connect():
            logger.info("Kafka service initialized successfully")
        else:
            logger.warning("Failed to connect to Kafka service")
    
    # Initialize change stream monitor
    if _change_stream_monitor is None and _kafka_service:
        _change_stream_monitor = ChangeStreamMonitor(
            mongodb_uri=settings.mongodb_uri,
            database_name=settings.mongodb_database,
            collection_name=settings.mongodb_collection,
            kafka_service=_kafka_service
        )
        
        _change_stream_monitor.start_monitoring()
        logger.info("Change stream monitor started")


def shutdown_repository() -> None:
    """Tear down the shared repository instance."""
    global _repository

    if _repository and _repository.is_connected():
        _repository.disconnect()

    _repository = None


def shutdown_kafka_services() -> None:
    """Tear down Kafka services."""
    global _kafka_service, _change_stream_monitor
    
    if _change_stream_monitor:
        _change_stream_monitor.stop_monitoring()
        _change_stream_monitor = None
    
    if _kafka_service:
        _kafka_service.disconnect()
        _kafka_service = None
    
    logger.info("Kafka services shut down")


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
