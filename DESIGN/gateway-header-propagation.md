# Gateway Header Propagation Pattern for Multi-Tenant Context

## Overview

This document describes the simplified pattern for passing tenant context (tier, clinic, user) from the agent to Lambda functions through AWS Bedrock AgentCore Gateway using **header propagation**.

## Problem Statement

In a multi-tenant healthcare system, Lambda functions invoked by MCP gateway tools need to know:
- **Tenant tier** (basic/premium) - for tier-specific logic
- **Clinic ID** (clinic-a, hospital-a) - for data isolation
- **S3 prefix** (basic-tier/clinic-a/) - for document scope

Initially, we attempted complex solutions like:
- ❌ Wrapping MCP tools to inject parameters
- ❌ Modifying API spec to include tenant parameters
- ❌ Custom tool decorators

**The simple solution:** Use AWS Bedrock AgentCore Gateway's built-in **header propagation** feature.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. AGENT (main_premium.py / main.py)                            │
│    • Extracts tenant context from API Gateway payload           │
│    • Sets CustomerSupportContext variables                      │
│    • Creates agent with tenant context                          │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. AGENT CLASS (agent.py)                                       │
│    • Creates MCPClient with headers:                            │
│      - X-Tenant-ID: premium                                     │
│      - X-Clinic-ID: hospital-a                                  │
│      - X-S3-Prefix: premium-tier/hospital-a/                    │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. MCP GATEWAY (configured with metadataConfiguration)          │
│    • Receives HTTP request with headers                         │
│    • Propagates allowedRequestHeaders to Lambda:                │
│      - X-Tenant-ID                                              │
│      - X-Clinic-ID                                              │
│      - X-S3-Prefix                                              │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. LAMBDA FUNCTION (lambda_function.py)                         │
│    • Reads headers from event['headers']                        │
│    • Routes to appropriate handler with tenant context          │
│    • Enforces data isolation per clinic                         │
└─────────────────────────────────────────────────────────────────┘
```

## Implementation

### 1. Gateway Target Configuration

**File:** `scripts/agentcore_gateway.py`

Configure the gateway target with `metadataConfiguration` to enable header propagation:

```python
# Configure header propagation for tenant context
metadata_config = {
    "allowedRequestHeaders": [
        "X-Tenant-ID",      # Tenant tier (basic/premium)
        "X-Clinic-ID",      # Clinic identifier
        "X-S3-Prefix"       # Document scope prefix
    ]
}

create_target_response = gateway_client.create_gateway_target(
    gatewayIdentifier=gateway_id,
    name=f"HealthcareLambda-{tier.title()}",
    description=f"Healthcare Lambda Target - {tier.title()} Tier",
    targetConfiguration=lambda_target_config,
    credentialProviderConfigurations=credential_config,
    metadataConfiguration=metadata_config,  # ← Enable header propagation
)
```

### 2. Agent MCP Client Setup

**File:** `agent_config_premium/agent.py` (and `agent_config/agent.py`)

The agent creates the MCP client with tenant context headers:

```python
self.gateway_client = MCPClient(
    lambda: streamablehttp_client(
        gateway_url,
        headers={
            "Authorization": f"Bearer {bearer_token}",
            "X-Tenant-ID": tenant_id,      # e.g., "premium"
            "X-Clinic-ID": clinic_id,      # e.g., "hospital-a"
            "X-S3-Prefix": s3_prefix       # e.g., "premium-tier/hospital-a/"
        },
    )
)
```

**Key Points:**
- Headers are set once during agent initialization
- No need to wrap or modify MCP tools
- Headers are automatically included in all MCP tool calls

### 3. Lambda Function Header Extraction

**File:** `prerequisite/lambda/python/lambda_function.py`

The Lambda function reads tenant context from propagated headers:

```python
def lambda_handler(event, context):
    # Extract tenant context from headers (propagated by gateway)
    headers = event.get('headers', {})
    tenant_id = headers.get('X-Tenant-ID', headers.get('x-tenant-id', 'basic'))
    clinic_id = headers.get('X-Clinic-ID', headers.get('x-clinic-id', 'demo-clinic'))
    s3_prefix = headers.get('X-S3-Prefix', headers.get('x-s3-prefix', 'basic-tier/demo-clinic/'))
    
    print(f"🏥 Healthcare request - Tenant: {tenant_id}, Clinic: {clinic_id}")
    print(f"📋 Headers received: {list(headers.keys())}")
    
    # Route to appropriate handler with tenant context
    if resource == "patient_context":
        return patient_context_handler(event, context)
```

**Key Points:**
- Check both capitalized and lowercase header names (HTTP headers are case-insensitive)
- Provide sensible defaults for missing headers
- Log received headers for debugging

## API Specification

**File:** `prerequisite/lambda/api_spec.json`

The API spec does NOT need tenant parameters - they're passed via headers:

```json
{
    "name": "patient_context",
    "description": "Retrieve patient metadata. Automatically filtered to requesting clinic.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "patient_id": {
                "type": "string",
                "description": "Unique patient identifier"
            }
        },
        "required": []
    }
}
```

**No tenant parameters needed!** The gateway handles header propagation transparently.

## Deployment Steps

### Initial Setup

1. **Create gateways with header propagation:**
   ```bash
   python scripts/agentcore_gateway.py create-all
   ```

### Updating Existing Gateways

If gateways already exist without header propagation:

1. **Delete existing gateways:**
   ```bash
   python scripts/agentcore_gateway.py delete-all --confirm
   ```

2. **Recreate with header propagation:**
   ```bash
   python scripts/agentcore_gateway.py create-all
   ```

3. **Deploy updated Lambda:**
   ```bash
   ./deploy.sh
   ```

## Testing & Verification

### Expected Logs

**Agent logs (CloudWatch):**
```
🔍 Extracted from payload - tier: premium, clinic_id: hospital-a, user_id: <uuid>
✅ Extracted tenant info from payload: {'tier': 'premium', 'clinic_id': 'hospital-a', ...}
🏥 Creating premium agent for tenant: tier=premium, clinic=hospital-a, user=<uuid>
```

**Lambda logs (CloudWatch):**
```
Event: {'list_patients': True, 'headers': {'X-Tenant-ID': 'premium', 'X-Clinic-ID': 'hospital-a', ...}}
🏥 Healthcare request - Tenant: premium, Clinic: hospital-a, Tool: patient_context
📋 Headers received: ['X-Tenant-ID', 'X-Clinic-ID', 'X-S3-Prefix', 'Authorization', ...]
```

### Troubleshooting

**Headers not received by Lambda:**
- ✅ Verify gateway target has `metadataConfiguration` with `allowedRequestHeaders`
- ✅ Check agent sets headers in MCP client initialization
- ✅ Recreate gateway targets if configuration was added after creation

**Wrong tenant context:**
- ✅ Verify API Gateway Lambda extracts correct values from JWT
- ✅ Check main.py/main_premium.py extracts from payload correctly
- ✅ Ensure agent receives correct tenant context during initialization

## Security Considerations

### Header Validation

The gateway only propagates headers explicitly listed in `allowedRequestHeaders`:
- ✅ Only whitelisted headers are forwarded
- ✅ Prevents header injection attacks
- ✅ Authorization header handled separately by gateway

### Data Isolation

Lambda functions enforce clinic-level isolation:
- ✅ DynamoDB queries filtered by `clinic_id`
- ✅ S3 document access scoped by `s3_prefix`
- ✅ No cross-clinic data access possible

### Best Practices

1. **Always validate headers** - Provide defaults for missing headers
2. **Log tenant context** - Include in all Lambda logs for audit trail
3. **Use case-insensitive checks** - HTTP headers can be lowercase or capitalized
4. **Never trust client headers** - Tenant context comes from authenticated JWT via API Gateway

## References

- [AWS Bedrock AgentCore Gateway Header Propagation](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-headers.html)
- [Healthcare Multi-Tenancy Architecture](./healthcare-multitenancy-architecture.md)
- [Technical Architecture](./technical-architecture.md)

## Related Files

- `scripts/agentcore_gateway.py` - Gateway creation with header propagation
- `agent_config_premium/agent.py` - Premium agent MCP client setup
- `agent_config/agent.py` - Basic agent MCP client setup
- `prerequisite/lambda/python/lambda_function.py` - Lambda header extraction
- `prerequisite/lambda/api_spec.json` - MCP tool API specification

## Changelog

- **2026-02-05**: Initial documentation of header propagation pattern
- Simplified from complex tool wrapping approach to native gateway feature
