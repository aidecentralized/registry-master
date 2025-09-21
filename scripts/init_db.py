#!/usr/bin/env python3
"""
Database initialization script for Global Registry Master
Creates indexes and optionally seeds initial data
"""

import logging
import os
import sys
from datetime import datetime

from app.core.config import get_settings
from app.db.repository import RegistryRepository
from app.models.registry import DirectAgentEntry, FederatedNamespaceEntry

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_sample_data():
    """Create sample data for testing"""
    
    # Sample direct agent entries
    direct_agents = [
        DirectAgentEntry(
            id="agent:nanda:uuid-1111",
            agent_id="nanda:uuid-1111",
            agent_name="urn:agent:nanda:TaxBot",
            facts_url="https://nanda.com/.well-known/agent-facts/1111",
            resolver_url="https://resolver.nanda.com/dispatch",
            tags=["tax.calculate", "finance.reports"],
            ttl=3600,
            signature="ed25519:abcdef123...",
            publisher="nanda",
            created_at=datetime.utcnow(),
            last_updated=datetime.utcnow()
        ),
        DirectAgentEntry(
            id="agent:acme:uuid-2222",
            agent_id="acme:uuid-2222", 
            agent_name="urn:agent:acme:WeatherBot",
            facts_url="https://acme.com/.well-known/agent-facts/2222",
            resolver_url="https://resolver.acme.com/dispatch",
            tags=["weather.forecast", "location.services"],
            ttl=1800,
            signature="ed25519:xyz789...",
            publisher="acme",
            created_at=datetime.utcnow(),
            last_updated=datetime.utcnow()
        )
    ]
    
    # Sample federated namespace entries
    federated_namespaces = [
        FederatedNamespaceEntry(
            id="ns:acme",
            namespace="acme",
            sub_index_url="https://registry.acme.com",
            registry_id="REG003",
            ttl=7200,
            signature="ed25519:fed-sig-123...",
            created_at=datetime.utcnow(),
            last_updated=datetime.utcnow()
        ),
        FederatedNamespaceEntry(
            id="ns:gov-japan",
            namespace="gov-japan",
            sub_index_url="https://registry.gov.jp",
            registry_id="REG004",
            ttl=14400,
            signature="ed25519:gov-sig-456...",
            created_at=datetime.utcnow(),
            last_updated=datetime.utcnow()
        )
    ]
    
    return direct_agents, federated_namespaces


def initialize_database(seed_data: bool = False) -> bool:
    """Initialize the registry database with indexes and optional seed data"""

    logger.info("Starting database initialization...")

    # Create database connection
    settings = get_settings()
    db = RegistryRepository(settings)

    if not db.connect():
        logger.error("Failed to connect to database")
        return False
    
    try:
        # Create indexes
        logger.info("Creating database indexes...")
        db.create_indexes()
        
        if seed_data:
            logger.info("Seeding sample data...")
            direct_agents, federated_namespaces = create_sample_data()
            
            # Insert direct agents
            for agent in direct_agents:
                success = db.insert_direct_agent(agent)
                if success:
                    logger.info(f"✓ Inserted agent: {agent.agent_name}")
                else:
                    logger.warning(f"✗ Failed to insert agent: {agent.agent_name}")
            
            # Insert federated namespaces
            for namespace in federated_namespaces:
                success = db.insert_federated_namespace(namespace)
                if success:
                    logger.info(f"✓ Inserted namespace: {namespace.namespace}")
                else:
                    logger.warning(f"✗ Failed to insert namespace: {namespace.namespace}")
        
        # Verify health
        health = db.get_health_status()
        logger.info(f"Database health: {health}")
        
        logger.info("Database initialization completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        return False
    finally:
        db.disconnect()


def main():
    """Main entry point"""
    seed_data = '--seed' in sys.argv or os.getenv('SEED_DATA', '').lower() == 'true'
    
    if seed_data:
        logger.info("Seed data flag detected - will populate sample data")
    
    success = initialize_database(seed_data=seed_data)
    
    if success:
        logger.info("🎉 Database initialization successful!")
        sys.exit(0)
    else:
        logger.error("❌ Database initialization failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
