"""MongoDB change stream monitor for Kafka publishing."""

import logging
import threading
import time
from typing import Dict, Any, Optional

from pymongo import MongoClient
from pymongo.errors import PyMongoError

from app.services.kafka_service import KafkaService

logger = logging.getLogger(__name__)


class ChangeStreamMonitor:
    """Monitors MongoDB change streams and publishes changes to Kafka from primary node only."""
    
    def __init__(self, mongodb_uri: str, database_name: str, collection_name: str, 
                 kafka_service: KafkaService):
        self.mongodb_uri = mongodb_uri
        self.database_name = database_name
        self.collection_name = collection_name
        self.kafka_service = kafka_service
        
        self._client: Optional[MongoClient] = None
        self._monitoring = False
        self._monitor_thread: Optional[threading.Thread] = None
        
    def start_monitoring(self):
        """Start monitoring change streams in a background thread."""
        if self._monitoring:
            logger.warning("Change stream monitoring is already running")
            return
            
        self._monitoring = True
        self._monitor_thread = threading.Thread(target=self._monitor_changes, daemon=True)
        self._monitor_thread.start()
        logger.info("Started change stream monitoring")
    
    def stop_monitoring(self):
        """Stop monitoring change streams."""
        self._monitoring = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=10)
        if self._client:
            self._client.close()
        logger.info("Stopped change stream monitoring")
    
    def _is_primary_node(self) -> bool:
        """Check if this MongoDB instance is the primary in the replica set."""
        try:
            if not self._client:
                self._client = MongoClient(self.mongodb_uri)
            
            # Check replica set status
            result = self._client.admin.command("isMaster")
            is_primary = result.get("ismaster", False)
            
            if is_primary:
                logger.debug("This node is the primary in the replica set")
            else:
                logger.debug("This node is not the primary in the replica set")
                
            return is_primary
            
        except Exception as e:
            logger.error(f"Failed to check if node is primary: {e}")
            return False
    
    def _monitor_changes(self):
        """Monitor MongoDB change streams and publish to Kafka."""
        retry_count = 0
        max_retries = 5
        
        while self._monitoring:
            try:
                if not self._is_primary_node():
                    logger.info("Not primary node, skipping change stream monitoring")
                    time.sleep(30)  # Check again in 30 seconds
                    continue
                
                if not self.kafka_service.is_connected():
                    logger.warning("Kafka not connected, attempting to reconnect...")
                    if not self.kafka_service.connect():
                        time.sleep(10)
                        continue
                
                # Connect to MongoDB if not connected
                if not self._client:
                    self._client = MongoClient(self.mongodb_uri)
                
                database = self._client[self.database_name]
                collection = database[self.collection_name]
                
                logger.info("Starting change stream monitoring on primary node")
                
                # Watch for changes in the collection
                with collection.watch(full_document='updateLookup') as stream:
                    retry_count = 0  # Reset retry count on successful connection
                    
                    for change in stream:
                        if not self._monitoring:
                            break
                        
                        # Check if still primary before processing each change
                        if not self._is_primary_node():
                            logger.info("No longer primary node, stopping change stream")
                            break
                        
                        self._process_change_event(change)
                        
            except PyMongoError as e:
                retry_count += 1
                logger.error(f"MongoDB error in change stream (attempt {retry_count}/{max_retries}): {e}")
                
                if retry_count >= max_retries:
                    logger.error("Max retries reached, stopping change stream monitoring")
                    break
                    
                # Close client to force reconnection
                if self._client:
                    self._client.close()
                    self._client = None
                
                # Exponential backoff
                sleep_time = min(60, 2 ** retry_count)
                logger.info(f"Retrying in {sleep_time} seconds...")
                time.sleep(sleep_time)
                
            except Exception as e:
                logger.error(f"Unexpected error in change stream monitoring: {e}")
                time.sleep(10)
        
        logger.info("Change stream monitoring stopped")
    
    def _process_change_event(self, change: Dict[str, Any]):
        """Process a single change event and publish to Kafka."""
        try:
            operation_type = change.get('operationType')
            document = change.get('fullDocument')
            document_key = change.get('documentKey', {})
            
            logger.debug(f"Processing change event: {operation_type} for document {document_key}")
            
            if operation_type == 'insert':
                if document:
                    self.kafka_service.publish_agent_added(document)
                    
            elif operation_type == 'update':
                if document:
                    self.kafka_service.publish_agent_updated(document)
                    
            elif operation_type == 'delete':
                # For delete operations, we only have the document key
                agent_id = document_key.get('agent_id') or str(document_key.get('_id', ''))
                self.kafka_service.publish_agent_revoked(agent_id)
                
            elif operation_type == 'replace':
                # Treat replace as update
                if document:
                    self.kafka_service.publish_agent_updated(document)
                    
            else:
                logger.debug(f"Ignoring operation type: {operation_type}")
                
        except Exception as e:
            logger.error(f"Failed to process change event: {e}")
            logger.debug(f"Change event details: {change}")