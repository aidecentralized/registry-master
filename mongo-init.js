// MongoDB initialization script
// This script runs when the MongoDB container starts for the first time

db = db.getSiblingDB('registry_master');

// Create the registry collection if it doesn't exist
db.createCollection('registry_master');

// Create indexes for optimal performance
print('Creating indexes...');

// By agent_id (fast unique resolution)
db.registry_master.createIndex({ agent_id: 1 }, { unique: true, sparse: true });
print('✓ Created index: agent_id');

// By agent_name (URN lookup)
db.registry_master.createIndex({ agent_name: 1 }, { unique: true, sparse: true });
print('✓ Created index: agent_name');

// By namespace (federated lookups)
db.registry_master.createIndex({ namespace: 1 }, { unique: true, sparse: true });
print('✓ Created index: namespace');

// By tags (capability search)
db.registry_master.createIndex({ tags: 1 });
print('✓ Created index: tags');

// By type for filtering
db.registry_master.createIndex({ type: 1 });
print('✓ Created index: type');

// Compound index for search optimization
db.registry_master.createIndex({ type: 1, tags: 1 });
print('✓ Created compound index: type + tags');

// By last_updated for maintenance queries
db.registry_master.createIndex({ last_updated: 1 });
print('✓ Created index: last_updated');

print('Database initialization completed successfully!');
print('Collection: registry_master');
print('Indexes created: 7 total');