import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from pymongo import ASCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import ConnectionFailure, DuplicateKeyError

from app.core.config import Settings
from app.models.registry import DirectAgentEntry, EntryType, FederatedNamespaceEntry

logger = logging.getLogger(__name__)


class RegistryRepository:
    """MongoDB repository backing the Global Registry Master service."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self.collection_name = settings.mongodb_collection

        self._client: Optional[MongoClient] = None
        self._database: Optional[Database] = None
        self._collection: Optional[Collection] = None

    def is_connected(self) -> bool:
        """Return whether the repository currently holds an active Mongo client."""
        return self._client is not None and self._collection is not None

    def connect(self) -> bool:
        """Establish connection to MongoDB with retry logic"""
        import time
        max_retries = 5
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                self._client = MongoClient(
                    self._settings.mongodb_uri,
                    serverSelectionTimeoutMS=5000,  # 5 second timeout
                    connectTimeoutMS=5000
                )
                # Test connection
                self._client.admin.command('ping')
                self._database = self._client[self._settings.mongodb_database]
                self._collection = self._database[self.collection_name]
                logger.info(f"Connected to MongoDB: {self._settings.mongodb_database}")
                return True
            except ConnectionFailure as e:
                logger.warning(f"MongoDB connection attempt {attempt + 1}/{max_retries} failed: {e}")
                if attempt < max_retries - 1:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 10)  # Exponential backoff, max 10s
                else:
                    logger.error(f"All MongoDB connection attempts failed")
                
                self._client = None
                self._database = None
                self._collection = None
        
        return False

    def disconnect(self):
        """Close MongoDB connection"""
        if self._client:
            self._client.close()
            logger.info("Disconnected from MongoDB")
        self._client = None
        self._database = None
        self._collection = None
    
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
            result = self._collection.insert_one(agent.model_dump(by_alias=True))
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
            result = self._collection.insert_one(namespace.model_dump(by_alias=True))
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
    
    def get_all_agents(self, entry_type: Optional[str] = None, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        """Get all agents with pagination support"""
        try:
            # Build match condition
            match_condition = {}
            if entry_type and entry_type != "all":
                if entry_type in ["direct", "federated"]:
                    match_condition["type"] = entry_type
                else:
                    raise ValueError(f"Invalid entry_type: {entry_type}. Must be 'direct', 'federated', or 'all'")
            
            # Get total count
            total_count = self._collection.count_documents(match_condition)
            
            # Build aggregation pipeline
            pipeline = [
                {"$match": match_condition},
                {"$sort": {"last_updated": -1}},  # Most recently updated first
                {"$skip": offset},
                {"$limit": limit},
                {
                    "$project": {
                        "_id": 0,  # Exclude ObjectId to avoid serialization issues
                        "type": 1,
                        "agent_id": 1,
                        "agent_name": 1,
                        "facts_url": 1,
                        "resolver_url": 1,
                        "tags": 1,
                        "publisher": 1,
                        "namespace": 1,
                        "sub_index_url": 1,
                        "registry_id": 1,
                        "ttl": 1,
                        "created_at": 1,
                        "last_updated": 1
                    }
                }
            ]
            
            # Execute query
            agents = list(self._collection.aggregate(pipeline))
            
            # Calculate pagination metadata
            has_next = (offset + limit) < total_count
            
            logger.info(f"Retrieved {len(agents)} agents (offset: {offset}, limit: {limit}, total: {total_count})")
            
            return {
                "agents": agents,
                "total_count": total_count,
                "limit": limit,
                "offset": offset,
                "has_next": has_next
            }
            
        except Exception as e:
            logger.error(f"Failed to get all agents: {e}")
            return {
                "agents": [],
                "total_count": 0,
                "limit": limit,
                "offset": offset,
                "has_next": False,
                "error": str(e)
            }

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
