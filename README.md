# Global Registry Master

A distributed agent registry service that acts as the entry point for finding and resolving agents globally. Stores namespaces and direct agent entries, returning lightweight pointers for full metadata resolution.

## Architecture

- **MongoDB**: Stores registry data with global replication
- **FastAPI**: REST API service for agent discovery and management  
- **Redis**: Caching layer (optional)
- **Docker**: Containerized deployment

## API Endpoints

### Public (Read)
- `GET /v1/index/search?searchparam=<json>` - Search agents using structured key-value pairs
- `GET /v1/agents/resolve?agent_name=<urn>` - Resolve agent URN to address
- `GET /healthz` - Health check

### Admin (Write, Secured)
- `POST /v1/admin/agent` - Add/update direct agent entry
- `POST /v1/admin/namespace` - Add/update federated namespace
- `POST /v1/admin/revoke` - Revoke an agent

## Data Structure

### Direct Agent Entry
```json
{
  "_id": "agent:nanda:uuid-1111",
  "type": "direct",
  "agent_id": "nanda:uuid-1111", 
  "agent_name": "urn:agent:nanda:TaxBot",
  "facts_url": "https://nanda.com/.well-known/agent-facts/1111",
  "resolver_url": "https://resolver.nanda.com/dispatch",
  "tags": ["tax.calculate", "finance.reports"],
  "ttl": 3600,
  "signature": "ed25519:abcdef123...",
  "publisher": "nanda",
  "created_at": "2025-09-11T12:00:00Z",
  "last_updated": "2025-09-11T12:00:00Z"
}
```

### Federated Namespace Entry
```json
{
  "_id": "ns:acme",
  "type": "federated", 
  "namespace": "acme",
  "sub_index_url": "https://registry.acme.com",
  "registry_id": "REG003",
  "ttl": 7200,
  "signature": "ed25519:fed-sig-123...",
  "created_at": "2025-09-11T12:00:00Z",
  "last_updated": "2025-09-11T12:00:00Z"
}
```

### Search Keys (MongoDB Fields)
- Multiple fields are combined with AND logic.
- Provide the fields which are required only. 
```json
{
  "agent_name": "string",   // Search by agent name (partial match, case-insensitive)
  "agent_id": "string",     // Search by agent ID (exact match)
  "tags": "string",         // Search within tags array (partial match, case-insensitive)
  "publisher": "string"     // Search by publisher (exact match)
}
```

**Valid Search Keys:**
- **agent_name**: Partial match with regex, case-insensitive (e.g., "urn:agent:nanda" matches agents with that prefix)
- **agent_id**: Exact match (e.g., "nanda:uuid-1111")
- **tags**: Partial match within tags array (e.g., "tax" matches "tax.calculate")
- **publisher**: Exact match (e.g., "nanda")
 

## Quick Start

### Using Docker Compose (Recommended)

1. **Clone and setup**:
   ```bash
   git clone <repository>
   cd register-master
   cp .env.example .env
   # Edit .env with your configuration
   ```

2. **Start services**:
   ```bash
   docker-compose up -d
   ```

3. **Initialize database** (optional, with sample data):
   ```bash
   docker-compose up db-init
   ```

4. **Access API**:
   - API: http://localhost:8000
   - Documentation: http://localhost:8000/docs
   - Health: http://localhost:8000/healthz

### Manual Development Setup

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Start MongoDB**:
   ```bash
   # Using Docker
   docker run -d -p 27017:27017 --name mongodb mongo:7.0
   ```

3. **Initialize database**:
   ```bash
   python init_db.py --seed
   ```

4. **Start API server**:
   ```bash
   uvicorn main:app --reload --port 8000
   ```

## Database Indexes

The system creates these indexes for optimal performance:

- `agent_id` (unique, sparse) - Fast agent resolution
- `agent_name` (unique, sparse) - URN lookup  
- `namespace` (unique, sparse) - Federated namespace lookup
- `tags` - Capability search
- `type` - Entry type filtering
- `[type, tags]` - Compound index for search optimization
- `last_updated` - Maintenance queries

## Authentication

Admin endpoints require Bearer token authentication:

```bash
# Set admin token in .env
ADMIN_TOKEN=your-secure-token

# Use in requests
curl -H "Authorization: Bearer your-secure-token" \
  -X POST http://localhost:8000/v1/admin/agent \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "test:123", ...}'
```

## Multi-VM Replica Set Deployment

### Deploy on Each VM
Deploy the same setup on all VMs (no configuration changes needed):
```bash
# On each VM (VM1, VM2, VM3, etc.)
git clone <repository>
cd register-master

# Start MongoDB and Redis
docker-compose up -d
```

### Initialize Replica Set
SSH into any one VM and initialize the replica set:
```bash
# For 3 VMs
./replica-init.sh 10.0.1.10:27017 10.0.1.11:27017 10.0.1.12:27017

# For 2 VMs  
./replica-init.sh 10.0.1.10:27017 10.0.1.11:27017
```

### Start API Service (Optional)
On VMs where you want the API service running:
```bash
# Update .env with replica set connection string
MONGODB_URI=mongodb://admin:password@10.0.1.10:27017,10.0.1.11:27017/registry_master?replicaSet=rs0&authSource=admin

# Start API service
docker-compose --profile api up -d registry-service
```

### Initialize Database (Optional)
After replica set is ready:
```bash
docker-compose --profile init up db-init
```

### Service Profiles
- **Default**: `docker-compose up -d` → MongoDB + Redis only
- **API**: `--profile api` → Adds registry-service  
- **Init**: `--profile init` → Runs database initialization

## Monitoring

- Health checks: `/healthz` endpoint
- Database status included in health response
- Ready for Route 53 health check integration
- Container health checks configured

## Example Usage

### Search for agents

**Structured search using MongoDB field names:**
```bash
# Search by agent name
curl "http://localhost:8000/v1/index/search?searchparam={\"agent_name\":\"urn:agent:nanda\"}"

# Search by agent ID
curl "http://localhost:8000/v1/index/search?searchparam={\"agent_id\":\"nanda:uuid-1111\"}"

# Search by capability tags
curl "http://localhost:8000/v1/index/search?searchparam={\"tags\":\"tax.calculate\"}"

# Search by publisher
curl "http://localhost:8000/v1/index/search?searchparam={\"publisher\":\"nanda\"}"

# Combined search with limit
curl "http://localhost:8000/v1/index/search?searchparam={\"publisher\":\"nanda\",\"tags\":\"tax\"}&limit=5"
```

### Resolve agent
```bash  
curl "http://localhost:8000/v1/agents/resolve?agent_name=urn:agent:nanda:TaxBot"
```

### Add agent (admin)
```bash
curl -H "Authorization: Bearer admin-secret-token" \
  -X POST http://localhost:8000/v1/admin/agent \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "nanda:uuid-1111",
    "agent_name": "urn:agent:nanda:TaxBot", 
    "facts_url": "https://nanda.com/.well-known/agent-facts/1111",
    "resolver_url": "https://resolver.nanda.com/dispatch",
    "tags": ["tax.calculate", "finance.reports"],
    "ttl": 3600,
    "signature": "ed25519:abcdef123...",
    "publisher": "nanda"
  }'
```

## License

[Your license here]