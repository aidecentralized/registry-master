#!/usr/bin/env python3
"""Test script to verify Kafka integration with the registry service."""

import json
import logging
import requests
import time
from kafka import KafkaConsumer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

KAFKA_BROKER = "34.229.1.253:9092"
KAFKA_TOPIC = "demo-topic"
REGISTRY_URL = "http://localhost:8000"

def test_kafka_consumer():
    """Test consuming messages from Kafka topic."""
    logger.info(f"Starting Kafka consumer for topic: {KAFKA_TOPIC}")
    
    try:
        consumer = KafkaConsumer(
            KAFKA_TOPIC,
            bootstrap_servers=KAFKA_BROKER,
            value_deserializer=lambda x: json.loads(x.decode('utf-8')),
            auto_offset_reset='latest',  # Start from latest messages
            consumer_timeout_ms=30000  # Wait 30 seconds for messages
        )
        
        logger.info("Kafka consumer connected successfully")
        logger.info("Waiting for messages... (30 second timeout)")
        
        message_count = 0
        for message in consumer:
            message_count += 1
            logger.info(f"Received message {message_count}:")
            logger.info(f"  Topic: {message.topic}")
            logger.info(f"  Partition: {message.partition}")
            logger.info(f"  Offset: {message.offset}")
            logger.info(f"  Value: {json.dumps(message.value, indent=2)}")
            
            # Stop after 5 messages or if no more messages
            if message_count >= 5:
                break
        
        if message_count == 0:
            logger.info("No messages received within timeout period")
        
        consumer.close()
        
    except Exception as e:
        logger.error(f"Error testing Kafka consumer: {e}")


def test_registry_operations():
    """Test registry operations that should trigger Kafka messages."""
    logger.info("Testing registry operations...")
    
    # Test data
    test_agent = {
        "agent_id": "test:kafka:agent-001",
        "agent_name": "urn:agent:test:KafkaTestBot",
        "facts_url": "https://test.example.com/.well-known/agent-facts/001",
        "tags": ["test.kafka", "demo.integration"],
        "ttl": 3600,
        "signature": "ed25519:test123",
        "publisher": "test"
    }
    
    try:
        # 1. Add agent
        logger.info("Adding test agent...")
        response = requests.post(
            f"{REGISTRY_URL}/v1/admin/agent",
            json=test_agent,
            headers={"Authorization": "Bearer admin-secret-token"}
        )
        
        if response.status_code == 201:
            logger.info("✅ Agent added successfully")
        else:
            logger.error(f"❌ Failed to add agent: {response.status_code} - {response.text}")
            return
        
        time.sleep(2)  # Allow time for change stream to process
        
        # 2. Update agent
        logger.info("Updating test agent...")
        update_data = {
            "tags": ["test.kafka", "demo.integration", "updated"],
            "ttl": 7200
        }
        
        response = requests.patch(
            f"{REGISTRY_URL}/v1/admin/agent/{test_agent['agent_id']}",
            json=update_data,
            headers={"Authorization": "Bearer admin-secret-token"}
        )
        
        if response.status_code == 200:
            logger.info("✅ Agent updated successfully")
        else:
            logger.error(f"❌ Failed to update agent: {response.status_code} - {response.text}")
        
        time.sleep(2)  # Allow time for change stream to process
        
        # 3. Delete agent
        logger.info("Deleting test agent...")
        response = requests.delete(
            f"{REGISTRY_URL}/v1/admin/revoke",
            json={"agent_id": test_agent['agent_id']},
            headers={"Authorization": "Bearer admin-secret-token"}
        )
        
        if response.status_code == 200:
            logger.info("✅ Agent deleted successfully")
        else:
            logger.error(f"❌ Failed to delete agent: {response.status_code} - {response.text}")
        
        time.sleep(2)  # Allow time for change stream to process
        
    except Exception as e:
        logger.error(f"Error testing registry operations: {e}")


def main():
    """Main test function."""
    logger.info("=== Kafka Integration Test ===")
    
    # Start consumer in background to capture messages
    logger.info("Step 1: Starting Kafka consumer...")
    
    # Start consumer thread
    import threading
    consumer_thread = threading.Thread(target=test_kafka_consumer)
    consumer_thread.daemon = True
    consumer_thread.start()
    
    # Wait a moment for consumer to start
    time.sleep(3)
    
    # Perform registry operations
    logger.info("Step 2: Performing registry operations...")
    test_registry_operations()
    
    # Wait for consumer to process messages
    logger.info("Step 3: Waiting for Kafka messages...")
    consumer_thread.join(timeout=35)
    
    logger.info("=== Test Complete ===")


if __name__ == "__main__":
    main()