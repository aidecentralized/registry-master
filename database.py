import os
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from pymongo import MongoClient, ASCENDING
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError, ConnectionFailure
from models import DirectAgentEntry, FederatedNamespaceEntry, EntryType

logger = logging.getLogger(__name__)


class RegistryDatabase:
    """MongoDB database component for Global Registry Master"""
    
    def __init__(self, connection_string: Optional[str] = None):
        self.connection_string = connection_string or os.getenv(
            'MONGODB_URI', 
            'mongodb://localhost:27017'
        )
        self.database_name = os.getenv('MONGODB_DATABASE', 'registry_master')
        self.collection_name = 'registry_master'
        
        self._client: Optional[MongoClient] = None
        self._database: Optional[Database] = None
        self._collection: Optional[Collection] = None
    
    def connect(self) -> bool:
        """Establish connection to MongoDB"""
        try:
            self._client = MongoClient(self.connection_string)
            # Test connection
            self._client.admin.command('ping')
            self._database = self._client[self.database_name]
            self._collection = self._database[self.collection_name]
            logger.info(f"Connected to MongoDB: {self.database_name}")
            return True
        except ConnectionFailure as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            return False
    
    def disconnect(self):
        """Close MongoDB connection"""
        if self._client:
            self._client.close()
            logger.info("Disconnected from MongoDB")
    
    def create_indexes(self):
        """Create required indexes for optimal performance"""
        logger.info("About to check collection connection")
        if getattr(self, '_collection', None) is None:
            logger.error("Collection is None!")
            raise RuntimeError("Database not connected")
        logger.info("Collection check passed")
        
        indexes = [
            # By agent_id (fast unique resolution)
            ("agent_id", {"unique": True, "sparse": True}),
            # By agent_name (URN lookup)
            ("agent_name", {"unique": True, "sparse": True}),
            # By namespace (federated lookups)
            ("namespace", {"unique": True, "sparse": True}),
            # By tags (capability search)
            ("tags", {}),
            # By type for filtering
            ("type", {}),
            # Compound index for search optimization
            (["type", "tags"], {}),
            # TTL index for automatic cleanup (optional)
            ("last_updated", {"expireAfterSeconds": None})  # Manual TTL handling
        ]
        
        for index_spec, options in indexes:
            try:
                logger.info(f"Creating index: {index_spec}")
                if isinstance(index_spec, str):
                    result = self._collection.create_index([(index_spec, ASCENDING)], **options)
                else:
                    index_fields = [(field, ASCENDING) for field in index_spec]
                    result = self._collection.create_index(index_fields, **options)
                logger.info(f"Created index: {index_spec} -> {result}")
            except Exception as e:
                logger.error(f"Index creation failed for {index_spec}: {e}")
                raise e
    
    def insert_direct_agent(self, agent: DirectAgentEntry) -> bool:
        """Insert a direct agent entry"""
        try:
            result = self._collection.insert_one(agent.dict())
            logger.info(f"Inserted direct agent: {agent.agent_id}")
            return True
        except DuplicateKeyError:
            logger.warning(f"Agent already exists: {agent.agent_id}")
            return False
        except Exception as e:
            logger.error(f"Failed to insert agent {agent.agent_id}: {e}")
            return False
    
    def insert_federated_namespace(self, namespace: FederatedNamespaceEntry) -> bool:
        """Insert a federated namespace entry"""
        try:
            result = self._collection.insert_one(namespace.dict())
            logger.info(f"Inserted federated namespace: {namespace.namespace}")
            return True
        except DuplicateKeyError:
            logger.warning(f"Namespace already exists: {namespace.namespace}")
            return False
        except Exception as e:
            logger.error(f"Failed to insert namespace {namespace.namespace}: {e}")
            return False
    
    def search_agents(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search agents by capability tags or name"""
        try:
            # Create text search pipeline
            pipeline = [
                {
                    "$match": {
                        "$or": [
                            {"tags": {"$regex": query, "$options": "i"}},
                            {"agent_name": {"$regex": query, "$options": "i"}},
                            {"agent_id": {"$regex": query, "$options": "i"}}
                        ],
                        "type": EntryType.DIRECT
                    }
                },
                {"$limit": limit},
                {
                    "$project": {
                        "agent_id": 1,
                        "agent_name": 1,
                        "facts_url": 1,
                        "resolver_url": 1,
                        "tags": 1,
                        "match_score": {"$literal": 1.0}  # Simple scoring for now
                    }
                }
            ]
            
            results = list(self._collection.aggregate(pipeline))
            logger.info(f"Search query '{query}' returned {len(results)} results")
            return results
        except Exception as e:
            logger.error(f"Search failed for query '{query}': {e}")
            return []

    def structured_search(self, query_dict: Dict[str, Any], limit: int = 10) -> List[Dict[str, Any]]:
        """Search agents using structured key-value queries"""
        try:
            # Build MongoDB query from structured input
            match_conditions = {"type": EntryType.DIRECT}
            
            # Process MongoDB field names directly
            for key, value in query_dict.items():
                if value:  # Skip empty values
                    if key == "agent_name":
                        # Partial match for agent names
                        match_conditions[key] = {"$regex": value, "$options": "i"}
                    elif key == "agent_id":
                        # Exact match for agent IDs
                        match_conditions[key] = value
                    elif key == "tags":
                        # Search within tags array
                        match_conditions[key] = {"$regex": value, "$options": "i"}
                    elif key == "publisher":
                        # Exact match for publisher
                        match_conditions[key] = value
            
            pipeline = [
                {"$match": match_conditions},
                {"$limit": limit},
                {
                    "$project": {
                        "agent_id": 1,
                        "agent_name": 1,
                        "facts_url": 1,
                        "resolver_url": 1,
                        "tags": 1,
                        "publisher": 1,
                        "match_score": {"$literal": 1.0}
                    }
                }
            ]
            
            results = list(self._collection.aggregate(pipeline))
            logger.info(f"Structured search with {query_dict} returned {len(results)} results")
            return results
            
        except Exception as e:
            logger.error(f"Structured search failed for query {query_dict}: {e}")
            return []
    
    def resolve_agent(self, agent_name: str) -> Optional[Dict[str, Any]]:
        """Resolve agent by URN to get its address information"""
        try:
            # First try direct lookup
            result = self._collection.find_one({
                "agent_name": agent_name,
                "type": EntryType.DIRECT
            })
            
            if result:
                return {
                    "agent_name": result["agent_name"],
                    "facts_url": result["facts_url"],
                    "resolver_url": result.get("resolver_url"),
                    "ttl": result["ttl"],
                    "type": EntryType.DIRECT
                }
            
            # If not found directly, check if it's in a federated namespace
            namespace = agent_name.split(":")[2] if ":" in agent_name else None
            if namespace:
                federated_entry = self._collection.find_one({
                    "namespace": namespace,
                    "type": EntryType.FEDERATED
                })
                
                if federated_entry:
                    return {
                        "agent_name": agent_name,
                        "facts_url": None,  # Must be resolved via sub-index
                        "resolver_url": federated_entry["sub_index_url"],
                        "ttl": federated_entry["ttl"],
                        "type": EntryType.FEDERATED,
                        "namespace": namespace
                    }
            
            logger.warning(f"Agent not found: {agent_name}")
            return None
            
        except Exception as e:
            logger.error(f"Resolution failed for agent '{agent_name}': {e}")
            return None
    
    def update_agent(self, agent_id: str, updates: Dict[str, Any]) -> bool:
        """Update an existing agent entry"""
        try:
            updates["last_updated"] = datetime.utcnow()
            result = self._collection.update_one(
                {"agent_id": agent_id},
                {"$set": updates}
            )
            success = result.modified_count > 0
            if success:
                logger.info(f"Updated agent: {agent_id}")
            else:
                logger.warning(f"No agent found to update: {agent_id}")
            return success
        except Exception as e:
            logger.error(f"Failed to update agent {agent_id}: {e}")
            return False
    
    def revoke_agent(self, agent_id: str) -> bool:
        """Remove an agent from the registry"""
        try:
            result = self._collection.delete_one({"agent_id": agent_id})
            success = result.deleted_count > 0
            if success:
                logger.info(f"Revoked agent: {agent_id}")
            else:
                logger.warning(f"No agent found to revoke: {agent_id}")
            return success
        except Exception as e:
            logger.error(f"Failed to revoke agent {agent_id}: {e}")
            return False
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get database health status"""
        try:
            # Ping database
            self._client.admin.command('ping')
            
            # Get collection stats
            stats = self._database.command("collStats", self.collection_name)
            
            return {
                "status": "healthy",
                "connected": True,
                "document_count": stats.get("count", 0),
                "storage_size": stats.get("storageSize", 0),
                "avg_obj_size": stats.get("avgObjSize", 0)
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "connected": False,
                "error": str(e)
            }