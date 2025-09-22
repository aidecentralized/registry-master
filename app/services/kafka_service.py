"""Kafka service for publishing MongoDB change events."""

import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from kafka import KafkaProducer
from kafka.errors import KafkaError

logger = logging.getLogger(__name__)


class KafkaService:
    """Service for publishing MongoDB change events to Kafka."""
    
    def __init__(self, bootstrap_servers: str, topic: str):
        self.bootstrap_servers = bootstrap_servers
        self.topic = topic
        self.producer: Optional[KafkaProducer] = None
        self._connected = False
    
    def connect(self) -> bool:
        """Initialize Kafka producer connection."""
        try:
            logger.info(f"Attempting to connect to Kafka broker: {self.bootstrap_servers}")
            self.producer = KafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                acks='all',  # Wait for all replicas to acknowledge
                retries=3,
                max_in_flight_requests_per_connection=1,
                request_timeout_ms=10000,
                metadata_max_age_ms=5000
            )
            self._connected = True
            logger.info(f"Successfully connected to Kafka: {self.bootstrap_servers}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Kafka broker {self.bootstrap_servers}: {e}")
            self._connected = False
            return False
    
    def disconnect(self):
        """Close Kafka producer connection."""
        if self.producer:
            self.producer.close()
            logger.info("Disconnected from Kafka")
        self._connected = False
        self.producer = None
    
    def is_connected(self) -> bool:
        """Check if Kafka producer is connected."""
        return self._connected and self.producer is not None
    
    def _serialize_document(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """Convert datetime objects to ISO strings for JSON serialization."""
        if not document:
            return document
            
        serialized = {}
        for key, value in document.items():
            if isinstance(value, datetime):
                serialized[key] = value.isoformat()
            elif key == "_id":
                # Convert ObjectId to string
                serialized[key] = str(value)
            else:
                serialized[key] = value
        return serialized
    
    def publish_change_event(self, operation: str, document: Dict[str, Any], 
                           document_id: str = None) -> bool:
        """Publish a change event to Kafka topic."""
        if not self.is_connected():
            logger.warning("Kafka producer not connected. Cannot publish event.")
            return False
        
        try:
            # Serialize the document to handle datetime objects
            serialized_document = self._serialize_document(document)
            
            event = {
                "timestamp": datetime.utcnow().isoformat(),
                "operation": operation,  # "insert", "update", "delete"
                "document_id": document_id,
                "document": serialized_document,
                "source": "registry-master"
            }
            
            future = self.producer.send(self.topic, value=event)
            # Block for synchronous send (optional)
            record_metadata = future.get(timeout=10)
            
            logger.info(f"Published {operation} event for document {document_id} "
                       f"to topic {self.topic} (partition: {record_metadata.partition}, "
                       f"offset: {record_metadata.offset})")
            return True
            
        except KafkaError as e:
            logger.error(f"Failed to publish event to Kafka: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error publishing to Kafka: {e}")
            return False
    
    def publish_agent_added(self, agent_data: Dict[str, Any]) -> bool:
        """Publish agent added event."""
        return self.publish_change_event(
            operation="insert",
            document=agent_data,
            document_id=agent_data.get("agent_id")
        )
    
    def publish_agent_updated(self, agent_data: Dict[str, Any]) -> bool:
        """Publish agent updated event."""
        return self.publish_change_event(
            operation="update", 
            document=agent_data,
            document_id=agent_data.get("agent_id")
        )
    
    def publish_agent_revoked(self, agent_id: str, agent_data: Dict[str, Any] = None) -> bool:
        """Publish agent revoked event."""
        return self.publish_change_event(
            operation="delete",
            document=agent_data or {"agent_id": agent_id},
            document_id=agent_id
        )