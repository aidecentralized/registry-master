# Global Registry Master

A distributed agent registry service that acts as the entry point for finding and resolving agents globally. Stores namespaces and direct agent entries, returning lightweight pointers for full metadata resolution.

## Architecture

- **MongoDB**: Stores registry data with global replication
- **FastAPI**: REST API service for agent discovery and management  
- **Redis**: Caching layer (optional)
- **Docker**: Containerized deployment

## API Endpoints

### Public (Read)
- `GET /v1/index/search?q=<term>` - Search agents by capability/name (legacy)
- `POST /v1/index/search` - Structured search with key-value queries
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

### Structured Search Query Format
```json
{
  "name": "string",        // Search by agent_name (partial match, case-insensitive)
  "agent-id": "string",    // Search by agent_id (exact match)
  "tags": "string",        // Search within tags array (partial match, case-insensitive)
  "publisher": "string"    // Search by publisher (exact match)
}
```

**Search Logic:**
- **name**: Partial match with regex, case-insensitive (e.g., "urn:" matches all URNs)
- **agent-id**: Exact match (e.g., "nanda:uuid-1111")
- **tags**: Partial match within tags array (e.g., "tax" matches "tax.calculate")
- **publisher**: Exact match (e.g., "nanda")
- Multiple fields are combined with AND logic

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

## Global Deployment

For production deployment across 12 regions:

1. **Provision infrastructure** with Terraform
2. **Deploy stack** with Ansible/Docker Compose per region
3. **Configure MongoDB replica set** across regions
4. **Setup Route 53** latency-based routing
5. **Bootstrap data** via admin APIs

## Monitoring

- Health checks: `/healthz` endpoint
- Database status included in health response
- Ready for Route 53 health check integration
- Container health checks configured

## Example Usage

### Search for agents

**Legacy search (GET):**
```bash
curl "http://localhost:8000/v1/index/search?q=tax&limit=5"
```

**Structured search (POST):**
```bash
# Search by agent name
curl -X POST "http://localhost:8000/v1/index/search" \
  -H "Content-Type: application/json" \
  -d '{"name": "urn:agent:nanda"}'

# Search by agent ID
curl -X POST "http://localhost:8000/v1/index/search" \
  -H "Content-Type: application/json" \
  -d '{"agent-id": "nanda:uuid-1111"}'

# Search by capability tags
curl -X POST "http://localhost:8000/v1/index/search" \
  -H "Content-Type: application/json" \
  -d '{"tags": "tax.calculate"}'

# Search by publisher
curl -X POST "http://localhost:8000/v1/index/search" \
  -H "Content-Type: application/json" \
  -d '{"publisher": "nanda"}'

# Combined structured search
curl -X POST "http://localhost:8000/v1/index/search?limit=5" \
  -H "Content-Type: application/json" \
  -d '{"publisher": "nanda", "tags": "tax"}'
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