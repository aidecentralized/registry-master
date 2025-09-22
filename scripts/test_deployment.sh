#!/bin/bash

# Test deployment script for registry service with Kafka integration
set -e

echo "=== Registry Service Deployment Test ==="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
REGISTRY_URL="http://localhost:8000"
KAFKA_BROKER="34.229.1.253:9092"
KAFKA_TOPIC="demo-topic"

echo -e "${YELLOW}Step 1: Building and starting services...${NC}"
docker-compose down --remove-orphans
docker-compose build
docker-compose up -d

echo -e "${YELLOW}Step 2: Waiting for services to start...${NC}"
sleep 10

# Check if registry service is running
echo -e "${YELLOW}Step 3: Checking registry service health...${NC}"
if curl -sf "${REGISTRY_URL}/healthz" > /dev/null; then
    echo -e "${GREEN}✅ Registry service is healthy${NC}"
else
    echo -e "${RED}❌ Registry service is not responding${NC}"
    echo "Service logs:"
    docker-compose logs registry-service
    exit 1
fi

# Initialize and check MongoDB replica set status
echo -e "${YELLOW}Step 4: Initializing MongoDB replica set...${NC}"
docker exec registry-mongodb mongosh --quiet --eval "
    try {
        // Try to get status first
        try {
            const status = rs.status();
            print('Replica set already initialized: ' + status.set);
        } catch (e) {
            // If not initialized, initialize it
            print('Initializing replica set...');
            rs.initiate({
                _id: 'rs0',
                members: [{ _id: 0, host: 'mongodb:27017' }]
            });
            
            // Wait for initialization
            let attempts = 0;
            while (attempts < 30) {
                try {
                    const status = rs.status();
                    if (status.members[0].stateStr === 'PRIMARY') {
                        print('✅ Replica set initialized successfully');
                        break;
                    }
                } catch (e) {
                    // Still initializing
                }
                sleep(1000);
                attempts++;
            }
            
            if (attempts >= 30) {
                print('❌ Replica set initialization timeout');
                exit(1);
            }
        }
    } catch (e) {
        print('❌ MongoDB replica set setup failed: ' + e);
        exit(1);
    }
"

# Test Kafka connectivity
echo -e "${YELLOW}Step 5: Testing Kafka connectivity...${NC}"
if python3 -c "
from kafka import KafkaProducer
import json
try:
    producer = KafkaProducer(
        bootstrap_servers='${KAFKA_BROKER}',
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )
    producer.send('${KAFKA_TOPIC}', {'test': 'connectivity'})
    producer.close()
    print('✅ Kafka connectivity test passed')
except Exception as e:
    print(f'❌ Kafka connectivity test failed: {e}')
    exit(1)
"; then
    echo -e "${GREEN}Kafka is accessible${NC}"
else
    echo -e "${RED}Kafka connectivity failed${NC}"
    exit 1
fi

# Test registry operations
echo -e "${YELLOW}Step 6: Testing registry operations...${NC}"

# Add a test agent
echo "Adding test agent..."
RESPONSE=$(curl -s -w "%{http_code}" -X POST "${REGISTRY_URL}/v1/admin/agent" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer admin-secret-token" \
    -d '{
        "agent_id": "test:deployment:agent-001",
        "agent_name": "urn:agent:test:DeploymentTestBot",
        "facts_url": "https://test.example.com/.well-known/agent-facts/001",
        "tags": ["test.deployment", "demo.integration"],
        "ttl": 3600,
        "signature": "ed25519:test123",
        "publisher": "test"
    }')

HTTP_CODE="${RESPONSE: -3}"
if [ "$HTTP_CODE" = "201" ]; then
    echo -e "${GREEN}✅ Agent added successfully${NC}"
else
    echo -e "${RED}❌ Failed to add agent (HTTP $HTTP_CODE)${NC}"
    exit 1
fi

sleep 2

# Search for the test agent
echo "Searching for test agent..."
SEARCH_RESPONSE=$(curl -s "${REGISTRY_URL}/v1/index/search?searchparam=%7B%22agent_name%22%3A%22DeploymentTestBot%22%7D")
if echo "$SEARCH_RESPONSE" | grep -q "DeploymentTestBot"; then
    echo -e "${GREEN}✅ Agent search successful${NC}"
else
    echo -e "${RED}❌ Agent search failed${NC}"
    echo "Search response: $SEARCH_RESPONSE"
    exit 1
fi

# Clean up test agent
echo "Cleaning up test agent..."
curl -s -X DELETE "${REGISTRY_URL}/v1/admin/revoke" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer admin-secret-token" \
    -d '{"agent_id": "test:deployment:agent-001"}' > /dev/null

echo -e "${GREEN}=== All tests passed! ✅ ===${NC}"
echo ""
echo "Services are running:"
echo "- Registry API: ${REGISTRY_URL}"
echo "- MongoDB: localhost:27017"
echo "- Redis: localhost:6379"
echo "- Kafka Integration: ${KAFKA_BROKER} (topic: ${KAFKA_TOPIC})"
echo ""
echo "To test Kafka integration manually:"
echo "  python3 test_kafka.py"
echo ""
echo "To stop services:"
echo "  docker-compose down"