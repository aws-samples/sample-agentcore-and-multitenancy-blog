# Multi-Tenant Healthcare Clinical Document Processing with Amazon Bedrock AgentCore

A multi-tenant AI clinical document processing platform built on Amazon Bedrock AgentCore, demonstrating complete tenant isolation across healthcare organizations with tier-based service levels.

## 🏗️ Architecture Overview

This project showcases advanced multi-tenancy patterns in AI agent systems for healthcare:

- **Complete Tenant Isolation**: Each clinic accesses only their documents via S3 prefixes and metadata filtering
- **Tier-Based Service Levels**: Basic (primary care) vs Premium (specialty care) with differentiated capabilities
- **Memory Isolation**: User-level memory separation via hierarchical `actor_id` patterns
- **Cost Attribution**: Per-clinic cost tracking via OpenTelemetry baggage and inference profile tags
- **Scalable Infrastructure**: Serverless architecture with AgentCore runtime

## 🎯 Healthcare Service Tiers

### Basic Tier - Primary Care Clinics
- **Document Search & Retrieval**: Search clinic-specific clinical documents
- **Document Summarization**: Summarize patient records and clinical notes (Nova Micro)
- **Rate Limits**: 0.5 req/sec, 5 daily requests (demo limits)

### Premium Tier - Specialty Care Organizations
- **All Basic Features**: Full access to document search, summarization, and extraction
- **Web Search**: Web search for current medical research and guidelines
- **Higher Limits**: 2 req/sec, 20 daily requests (demo limits)

## 🚀 Quick Start

### Prerequisites

- **AWS Account** with Bedrock access enabled 
- **AWS CLI** configured with appropriate permissions
- **Python 3.8+** and pip

### One-Command Deployment

```bash
git clone <repository-url>
cd agentcore-multitenancy
chmod +x deploy.sh
./deploy.sh
```

### Launch the Demo

```bash
source .venv/bin/activate
streamlit run app.py --server.port 8501

# Log in using credentials stored under /credentials/test_user.json
```

Access the demo at `http://localhost:8501`

### Cleanup

```bash
chmod +x scripts/cleanup.sh
./scripts/cleanup.sh
```

## 🏛️ Technical Architecture

### Key Components

- **Amazon Bedrock AgentCore**: Serverless AI agent runtime with memory isolation
- **AgentCore Memory**: Tier-specific memory resources with namespace templates for user isolation
- **Strands Framework**: Agent orchestration and tool integration
- **Agentcore Gateway**: Tool integration and routing
- **Amazon Cognito**: JWT-based authentication with `custom:tenant_id` and `custom:clinic_id`
- **Knowledge Bases**: Clinic-isolated document retrieval with metadata filtering
- **SSM Parameter Store**: Configuration management

### Memory Isolation Architecture

Each user gets a unique `actor_id` combining tier, clinic, and user:

```
actor_id = "{tier}-{clinic_id}-{user_id}"
# Example: "premium-hospital-a-04684408-00d1-7087-e9c6-e033aff7f0ee"
```

Namespace templates ensure complete isolation:
```
clinic/{actorId}/facts/{sessionId}
clinic/{actorId}/summaries/{sessionId}
clinic/{actorId}/preferences
```


## 📊 Memory Cost Tracking with CloudWatch Logs Insights

AgentCore Memory automatically emits structured logs for every memory operation. These logs contain tenant-specific namespace information that enables per-clinic cost tracking without any additional instrumentation.

### Log Group Locations

| Tier    | Log Group Path                                                                            |
| ------- | ----------------------------------------------------------------------------------------- |
| Basic   | `/aws/vendedlogs/bedrock-agentcore/memory/APPLICATION_LOGS/<basic-memory-resource-id>`   |
| Premium | `/aws/vendedlogs/bedrock-agentcore/memory/APPLICATION_LOGS/<premium-memory-resource-id>` |

Log streams are named `BedrockAgentCoreMemory_ApplicationLogs`.

### CloudWatch Logs Insights Queries

Navigate to **CloudWatch → Logs Insights**, select the appropriate memory log group, and set the time range to cover your target period.

#### 1. Memory Events Per Clinic Per Day (with Cost Estimate)

```sql
fields @timestamp, namespace
| parse namespace /clinic\/(?<tier>basic|premium)-(?<clinic_id>.+?)-(?<user_id>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\//
| stats count() as memory_events, count() * 0.000001 as estimated_cost_usd
  by tier, clinic_id, bin(1d) as day
| sort day desc
```

#### 2. Consolidation Events Per Clinic (Long-Term Memory Writes)

```sql
fields @timestamp, namespace, body.log
| filter body.log like /consolidation/
| parse namespace /clinic\/(?<tier>basic|premium)-(?<clinic_id>.+?)-(?<user_id>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\//
| stats count() as consolidations by tier, clinic_id
```

#### 3. Per-User Memory Activity

```sql
fields @timestamp, namespace
| parse namespace /clinic\/(?<tier>basic|premium)-(?<clinic_id>.+?)-(?<user_id>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\//
| stats count() as events by tier, clinic_id, user_id
| sort events desc
```

#### 4. All Activity for a Specific Clinic

```sql
fields @timestamp, namespace, body.log, severityText
| filter namespace like /hospital-a/
| sort @timestamp desc
| limit 100
```

### Cost Reference

| Operation              | Cost                   |
| ---------------------- | ---------------------- |
| Memory event (write)   | ~$0.000001 per event   |
| Memory retrieval (read)| ~$0.000004 per call    |
| Long-term storage      | ~$0.10 per GB/month    |


## 🤝 Contributing

1. **Fork the repository**
2. **Create a feature branch**: `git checkout -b feature/new-clinic`
3. **Follow the steering guidelines**: Check `.kiro/steering/` for development standards
4. **Test thoroughly**: Run the full test suite
5. **Submit a pull request**: Include detailed description and test results

---
