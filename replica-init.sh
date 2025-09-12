#!/bin/bash

# MongoDB Replica Set Initialization Script
# Usage: ./replica-init.sh <primary_ip:port> <secondary1_ip:port> [secondary2_ip:port] [...]
# Example: ./replica-init.sh 10.0.1.10:27017 10.0.1.11:27017 10.0.1.12:27017

if [ $# -lt 1 ]; then
    echo "Usage: $0 <primary_ip:port> [secondary1_ip:port] [secondary2_ip:port] [...]"
    echo "Examples:"
    echo "  Single node: $0 localhost:27017"
    echo "  Multi nodes: $0 10.0.1.10:27017 10.0.1.11:27017 10.0.1.12:27017"
    exit 1
fi

REPLICA_SET_NAME=${REPLICA_SET_NAME:-"rs0"}
USERNAME=${MONGO_USERNAME:-"admin"}
PASSWORD=${MONGO_PASSWORD:-"password"}
AUTH_DB=${MONGO_AUTH_DB:-"admin"}

PRIMARY_HOST=$1
shift
SECONDARY_HOSTS=("$@")

echo "=== MongoDB Replica Set Initialization ==="
echo "Replica Set: $REPLICA_SET_NAME"
echo "Primary: $PRIMARY_HOST"
echo "Secondaries: ${SECONDARY_HOSTS[*]}"
echo ""

# Wait for primary to be ready
echo "Waiting for primary ($PRIMARY_HOST) to be ready..."
until docker run --rm --network register-master_registry-network mongo:7.0 mongosh --host "$PRIMARY_HOST" --username "$USERNAME" --password "$PASSWORD" --authenticationDatabase "$AUTH_DB" --eval "print(\"Primary ready\")" > /dev/null 2>&1; do
    echo "  Still waiting for $PRIMARY_HOST..."
    sleep 3
done
echo "✓ Primary is ready"

# Wait for all secondaries to be ready (if any)
if [ ${#SECONDARY_HOSTS[@]} -gt 0 ]; then
    for secondary in "${SECONDARY_HOSTS[@]}"; do
        echo "Waiting for secondary ($secondary) to be ready..."
        until docker run --rm --network register-master_registry-network mongo:7.0 mongosh --host "$secondary" --username "$USERNAME" --password "$PASSWORD" --authenticationDatabase "$AUTH_DB" --eval "print(\"Secondary ready\")" > /dev/null 2>&1; do
            echo "  Still waiting for $secondary..."
            sleep 3
        done
        echo "✓ Secondary $secondary is ready"
    done
else
    echo "ℹ️  Single node replica set - no secondaries to wait for"
fi

echo ""
echo "All MongoDB instances are ready. Initializing replica set..."

# Build replica set configuration
RS_CONFIG="{"
RS_CONFIG="$RS_CONFIG _id: \"$REPLICA_SET_NAME\","
RS_CONFIG="$RS_CONFIG members: ["

# Add primary (id: 0, priority: 2)
RS_CONFIG="$RS_CONFIG { _id: 0, host: \"$PRIMARY_HOST\", priority: 2 }"

# Add secondaries (id: 1+, priority: 1)
member_id=1
for secondary in "${SECONDARY_HOSTS[@]}"; do
    RS_CONFIG="$RS_CONFIG, { _id: $member_id, host: \"$secondary\", priority: 1 }"
    ((member_id++))
done

RS_CONFIG="$RS_CONFIG ]"
RS_CONFIG="$RS_CONFIG }"

echo "Replica set configuration:"
echo "$RS_CONFIG"
echo ""

# Initialize replica set
docker run --rm --network register-master_registry-network mongo:7.0 mongosh --host "$PRIMARY_HOST" --username "$USERNAME" --password "$PASSWORD" --authenticationDatabase "$AUTH_DB" --eval "rs.initiate($RS_CONFIG)"

if [ $? -eq 0 ]; then
    echo "✓ Replica set initialization command completed"
else
    echo "✗ Replica set initialization failed"
    exit 1
fi

echo ""
echo "Waiting for replica set to stabilize (30 seconds)..."
sleep 30

# Check replica set status
echo ""
echo "=== Replica Set Status ==="
mongosh --host "$PRIMARY_HOST" --username "$USERNAME" --password "$PASSWORD" --authenticationDatabase "$AUTH_DB" --eval "rs.status()" || {
    echo "Warning: Could not retrieve replica set status"
}

echo ""
echo "=== Replica Set Configuration ==="
mongosh --host "$PRIMARY_HOST" --username "$USERNAME" --password "$PASSWORD" --authenticationDatabase "$AUTH_DB" --eval "rs.conf()" || {
    echo "Warning: Could not retrieve replica set configuration"
}

echo ""
echo "=== Replica Set Initialization Complete ==="
echo "Connection string format:"
echo "mongodb://$USERNAME:$PASSWORD@$PRIMARY_HOST,$(IFS=,; echo "${SECONDARY_HOSTS[*]}")/<database>?replicaSet=$REPLICA_SET_NAME&authSource=$AUTH_DB"