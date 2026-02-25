# Multi-Tenant Healthcare Agent with Amazon Bedrock AgentCore

A multi-tenant AI clinical document assistant built on Amazon Bedrock AgentCore, demonstrating common multi-tenancy concerns when building agentic SaaS applications.

## What It Does

Healthcare staff can search, summarize, and analyze patient records and clinical documents. Each clinic is fully isolated — they can only see their own data.

## Multi-Tenancy Patterns Demonstrated

### 1. Data Isolation — Knowledge Base Metadata Filtering
Each clinic's documents are tagged with a `clinic_id` metadata field. At query time, the agent's `retrieve_clinic_documents` tool applies a metadata filter so tenants only retrieve their own documents.

```python
# agent/tools/retrieve_clinic_documents.py
response = client.retrieve(
    knowledgeBaseId=kb_id,
    retrievalQuery={"text": query},
    retrievalConfiguration={
        "vectorSearchConfiguration": {
            "filter": {"equals": {"key": "clinic_id", "value": clinic_id}}
        }
    },
)
```

### 2. Memory Isolation — Hierarchical actor_id
Conversation history is scoped per-tenant using a hierarchical `actor_id`:

```
actor_id = "{tier}-{clinic_id}-{user_id}"
# e.g., "premium-hospital-a-04684408-00d1-7087-e9c6-e033aff7f0ee"
```

Memory namespaces ensure complete isolation:
```
clinic/{actorId}/facts/{sessionId}
clinic/{actorId}/preferences
```

### 3. Tier-Based Routing — Single Agent, Config-Driven
One `HealthcareAgent` class serves both tiers. Differences are driven by a `TIER_CONFIG` dict:

| Concern | Basic | Premium |
|---------|-------|---------|
| Model | Nova Micro | Claude Sonnet |
| Tools | Document search, patient context | + Web search |
| Gateway | HealthcareLambda-Basic | HealthcareLambda-Premium |
| Inference Profile | Basic cost tag | Premium cost tag |

### 4. Authentication & Tenant Identity — Cognito JWT
Amazon Cognito issues JWTs with custom attributes (`custom:tenant_id`, `custom:clinic_id`). The API Gateway Lambda extracts these claims and forwards them to the agent as payload fields.

### 5. Cost Attribution — OpenTelemetry Baggage + Inference Profiles
Per-tenant cost tracking via:
- OpenTelemetry baggage propagation (`tier`, `clinic_id`, `actor_id`)
- Bedrock inference profiles with tier-specific tags

### 6. Gateway Header Propagation
Tenant context flows through AgentCore Gateway via headers:
```
X-Tenant-ID: premium
X-Clinic-ID: hospital-a
X-S3-Prefix: premium-tier/hospital-a/
```

## Service Tiers

- **Basic** — Primary care clinics (A–D). Document search, summarization via Nova Micro.
- **Premium** — Specialty care orgs (Hospitals A–B, Clinics E–F). All basic features plus web search for medical research, Claude Sonnet model.

## Quick Start

### Prerequisites

- AWS account with Bedrock access enabled
- AWS CLI configured with appropriate permissions
- Python 3.12+

### Deploy

```bash
git clone <repository-url>
cd agentcore-multitenancy

python3 -m venv .venv
source .venv/bin/activate
pip install -r dev-requirements.txt

chmod +x deploy.sh
./deploy.sh
```

### Run the Web UI

```bash
streamlit run app.py --server.port 8501
```

Log in with test credentials from `credentials/test_users.json` (generated during deployment).

## Project Structure

```
├── main.py                        # Unified AgentCore entrypoint (AGENT_TIER env var)
├── app.py                         # Streamlit web UI
├── agent/                         # Agent code (single module, both tiers)
│   ├── agent.py                   # HealthcareAgent — tier-configurable via TIER_CONFIG
│   ├── agent_task.py              # Async task runner
│   ├── context.py                 # TenantContext — ContextVar-based tenant state
│   ├── memory_hook.py             # Strands MemoryHook for AgentCore Memory
│   └── tools/
│       └── retrieve_clinic_documents.py  # KB retrieval with clinic filtering
├── app_modules/                   # Streamlit UI
│   ├── auth.py                    # Cognito OAuth2 PKCE flow
│   └── chat.py                    # ChatManager (API Gateway path)
├── scripts/                       # Deployment scripts
├── prerequisite/                  # CloudFormation templates, Lambda code, sample docs
├── test/                          # Test suite
└── config/                        # Deployment configuration templates
```

## Cleanup

```bash
chmod +x scripts/cleanup.sh
./scripts/cleanup.sh
```
