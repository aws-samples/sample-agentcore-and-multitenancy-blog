## Multi-Tenant Cost Tracking Strategy

### Overview

Tracking costs per tenant (clinic) is critical for demonstrating multi-tenancy capabilities and enabling accurate billing/chargeback. AgentCore provides multiple mechanisms for cost tracking across Runtime, Memory, and model usage.

### Cost Tracking Approaches

#### 1. Application Inference Profiles (Recommended for Model Costs)

**What**: Custom inference profiles with tags for tenant identification
**Best For**: Tracking Bedrock model invocation costs per tenant
**Current Status**: ✅ Already implemented with tier-level profiles

**Existing Setup** (from `scripts/create_inference_profiles.py`):
```python
# Current profiles (tier-level)
inference_profile_mapping = {
    "basic": "arn:aws:bedrock:us-east-1:ACCOUNT:application-inference-profile/g5oiel8xmjz5",
    "premium": "arn:aws:bedrock:us-east-1:ACCOUNT:application-inference-profile/pxttfsxmxl5o"
}

# Tags on existing profiles
tags = [
    {'key': 'Project', 'value': 'CustomerSupport'},
    {'key': 'Tier', 'value': 'Basic'}  # or 'Premium'
]
```

**Enhancement for Clinic-Level Tracking**:

Extend the existing script to create profiles per clinic:

```python
# Enhanced create_inference_profiles.py
def create_clinic_inference_profiles():
    """Create inference profiles per clinic for granular cost tracking"""
    
    bedrock = boto3.client('bedrock')
    ssm = boto3.client('ssm')
    
    # Define clinics
    clinics = {
        'basic': [
            {'id': 'clinic-a', 'name': 'Family Practice'},
            {'id': 'clinic-b', 'name': 'Urgent Care'},
            {'id': 'clinic-c', 'name': 'Pediatrics'}
        ],
        'premium': [
            {'id': 'hospital-a', 'name': 'Multi-specialty Hospital'},
            {'id': 'clinic-e', 'name': 'Cardiology Clinic'},
            {'id': 'clinic-f', 'name': 'Oncology Clinic'}
        ]
    }
    
    # Model mapping (using system-defined inference profiles)
    models = {
        'basic': 'us.amazon.nova-micro-v1:0',
        'premium': 'global.anthropic.claude-sonnet-4-5-20250929-v1:0'  # Claude 4.5 Sonnet
    }
    
    profile_mapping = {}
    
    for tier, clinic_list in clinics.items():
        for clinic in clinic_list:
            profile_name = f"healthcare-{tier}-{clinic['id']}"
            
            # Create profile
            response = bedrock.create_application_inference_profile(
                inferenceProfileName=profile_name,
                description=f"Profile for {clinic['name']} ({tier} tier)",
                modelSource={'copyFrom': models[tier]},
                tags=[
                    {'key': 'Project', 'value': 'HealthcareDemo'},
                    {'key': 'Tier', 'value': tier},
                    {'key': 'ClinicID', 'value': clinic['id']},
                    {'key': 'ClinicName', 'value': clinic['name']},
                    {'key': 'Environment', 'value': 'demo'}
                ]
            )
            
            profile_arn = response['inferenceProfileArn']
            profile_mapping[f"{tier}-{clinic['id']}"] = profile_arn
            
            # Store in SSM
            ssm.put_parameter(
                Name=f"/app/healthcare/inference_profiles/{tier}/{clinic['id']}",
                Value=profile_arn,
                Type='String',
                Overwrite=True
            )
            
            print(f"✅ Created profile: {profile_name}")
    
    return profile_mapping
```

**Update Agent Configuration**:

```python
# In agent_config/agent.py and agent_config_premium/agent.py
from .utils import get_ssm_parameter

class CustomerSupport:
    def __init__(self, tenant_id: str, clinic_id: str, ...):
        # Get clinic-specific inference profile from SSM
        tier = tenant_id  # 'basic' or 'premium'
        
        try:
            # Try clinic-specific profile first
            profile_arn = get_ssm_parameter(
                f"/app/healthcare/inference_profiles/{tier}/{clinic_id}"
            )
            print(f"✅ Using clinic-specific profile for {clinic_id}")
        except:
            # Fallback to tier-level profile
            profile_arn = get_ssm_parameter(
                f"/app/customersupport/inference_profiles/{tier}_arn"
            )
            print(f"⚠️ Using tier-level profile for {tier}")
        
        self.model_id = profile_arn
        self.model = BedrockModel(model_id=self.model_id)
```

**Benefits**:
- ✅ Automatic cost allocation in AWS Cost Explorer per clinic
- ✅ Integration with AWS Budgets for per-clinic alerts
- ✅ Builds on existing infrastructure
- ✅ Works with AWS Cost and Usage Reports (CUR)
- ✅ Granular tracking: Clinic A vs Clinic B costs

#### 2. Request Metadata (Granular Tracking) (optional, might not be in MVP)

**What**: Include tenant metadata in every Bedrock API call
**Best For**: Detailed usage analytics and custom reporting
**Implementation**:

```python
# Add metadata to Bedrock Converse API calls
response = bedrock_runtime.converse(
    modelId='global.anthropic.claude-sonnet-4-5-20250929-v1:0',
    messages=[...],
    requestMetadata={
        'tenantId': 'clinic-a',
        'tier': 'basic',
        'sessionId': session_id,
        'userId': user_id,
        'timestamp': str(int(time.time())),
        'feature': 'document-search'
    }
)
```

**Benefits**:
- Granular tracking (per-request, per-feature, per-user)
- Captured in CloudWatch Logs for custom analytics
- Can track beyond just costs (latency, errors, usage patterns)
- Enables tenant-specific dashboards

#### 3. AgentCore Observability (Runtime & Memory Costs)

**What**: Built-in telemetry for AgentCore services
**Best For**: Tracking Runtime, Memory, and tool usage costs per tenant
**Current Status**: 
- ✅ Runtime observability: Already enabled in your `.bedrock_agentcore.yaml`
- ⚠️ Memory observability: **Requires manual setup** (see below)
- ⚠️ Gateway observability: **Requires manual setup** (see below)

**How It Works**:

AgentCore Observability tracks:
- **Runtime Costs**: ✅ Automatic - CPU and memory consumption per agent invocation
- **Memory Costs**: ⚠️ Requires setup - Short-term memory events and long-term memory retrievals
- **Tool Costs**: ⚠️ Requires setup - Gateway, Browser, Code Interpreter usage
- **Session Metrics**: ✅ Automatic - Duration, token usage, error rates

**Pricing Model** (Consumption-Based):
```
Runtime:
- CPU: $0.000011 per vCPU-second
- Memory: $0.0000012 per GB-second
- Billed per second of actual usage

Memory:
- Short-term events: $0.000001 per event
- Long-term storage: $0.10 per GB-month
- Retrieval calls: $0.000004 per call

Observability:
- Telemetry generation: $0.000001 per span
- Storage: $0.50 per GB-month
- Queries: $0.005 per GB scanned
```

**Implementation for Multi-Tenant Cost Tracking**:

**Step 1: Enable Memory Observability (One-Time Setup)**

Memory observability is **not automatic**. You must configure log destinations for each Memory resource:

```python
# In scripts/setup_memory_observability.py
import boto3

def enable_memory_observability(memory_id, account_id, region='us-east-1'):
    """
    Enable observability for AgentCore Memory resource
    Required for cost tracking and tenant usage monitoring
    """
    logs_client = boto3.client('logs', region_name=region)
    
    # Memory resource ARN
    memory_arn = f"arn:aws:bedrock-agentcore:{region}:{account_id}:memory/{memory_id}"
    
    # Step 1: Create log group for memory logs
    log_group_name = f'/aws/vendedlogs/bedrock-agentcore/memory/APPLICATION_LOGS/{memory_id}'
    try:
        logs_client.create_log_group(logGroupName=log_group_name)
        print(f"✅ Created log group: {log_group_name}")
    except logs_client.exceptions.ResourceAlreadyExistsException:
        print(f"ℹ️ Log group already exists: {log_group_name}")
    
    log_group_arn = f'arn:aws:logs:{region}:{account_id}:log-group:{log_group_name}'
    
    # Step 2: Create delivery source for logs
    logs_source_response = logs_client.put_delivery_source(
        name=f"{memory_id}-logs-source",
        logType="APPLICATION_LOGS",
        resourceArn=memory_arn
    )
    
    # Step 3: Create delivery source for traces
    traces_source_response = logs_client.put_delivery_source(
        name=f"{memory_id}-traces-source",
        logType="TRACES",
        resourceArn=memory_arn
    )
    
    # Step 4: Create delivery destinations
    logs_destination_response = logs_client.put_delivery_destination(
        name=f"{memory_id}-logs-destination",
        deliveryDestinationType='CWL',
        deliveryDestinationConfiguration={
            'destinationResourceArn': log_group_arn,
        }
    )
    
    traces_destination_response = logs_client.put_delivery_destination(
        name=f"{memory_id}-traces-destination",
        deliveryDestinationType='XRAY'
    )
    
    # Step 5: Create deliveries (connect sources to destinations)
    logs_delivery = logs_client.create_delivery(
        deliverySourceName=logs_source_response['deliverySource']['name'],
        deliveryDestinationArn=logs_destination_response['deliveryDestination']['arn']
    )
    
    traces_delivery = logs_client.create_delivery(
        deliverySourceName=traces_source_response['deliverySource']['name'],
        deliveryDestinationArn=traces_destination_response['deliveryDestination']['arn']
    )
    
    print(f"✅ Observability enabled for Memory: {memory_id}")
    return {
        'logs_delivery_id': logs_delivery['delivery']['id'],
        'traces_delivery_id': traces_delivery['delivery']['id'],
        'log_group_name': log_group_name
    }

# Setup for both memory resources
account_id = boto3.client('sts').get_caller_identity()['Account']
enable_memory_observability('healthcare-basic-memory', account_id)
enable_memory_observability('healthcare-premium-memory', account_id)
```

**Alternative: Enable via AWS Console**
1. Navigate to: AgentCore Console → Memory Resources
2. Select your memory resource (e.g., `healthcare-basic-memory`)
3. Click "Configure observability"
4. Enable "Application logs" → Select CloudWatch Logs
5. Enable "Traces" → Select AWS X-Ray
6. Save configuration
7. Repeat for `healthcare-premium-memory`

**Step 2: Add Tenant Context via OpenTelemetry Baggage**

After Memory observability is enabled, add tenant context to propagate through all operations:

```python
# In main.py and main_premium.py - Add tenant context to all operations
from opentelemetry import baggage, context

@app.entrypoint
async def invoke(payload, context_obj):
    # Extract tenant info (already implemented)
    tenant_info = process_tenant_context(payload, context_obj.headers or {})
    
    # Set OpenTelemetry baggage for cost attribution
    # This propagates tenant context to all spans, metrics, and logs
    ctx = baggage.set_baggage("tenant_id", tenant_info['tenant_key'])
    ctx = baggage.set_baggage("tier", tenant_info['tier'])
    ctx = baggage.set_baggage("clinic_id", tenant_info['clinic_id'])
    ctx = baggage.set_baggage("actor_id", tenant_info['actor_id'])  # For memory isolation
    context.attach(ctx)
    
    # All subsequent operations will include this tenant context
    # Runtime costs: Automatically tagged (no setup needed)
    # Memory costs: Tagged after observability setup above
    # Model costs: Tagged via inference profile
    response = await agent_task(...)
    return response
```

**How It Works**:
1. ✅ **Runtime observability**: Already enabled in your `.bedrock_agentcore.yaml`
2. ⚠️ **Memory observability**: Requires one-time setup per Memory resource (see above)
3. ✅ **ADOT SDK automatically configured** by AgentCore runtime
4. ✅ **Baggage propagates** to all spans, metrics, and logs
5. ✅ **CloudWatch receives** tenant-tagged telemetry after setup

**Optional: Enhanced Observability with Custom Headers**:

You can also pass tenant context via HTTP headers when invoking agents:

```python
# When invoking agent via API
headers = {
    'Authorization': f'Bearer {token}',
    'X-Amzn-Bedrock-AgentCore-Runtime-Session-Id': session_id,
    'baggage': f'tenant_id={tenant_key},tier={tier},clinic_id={clinic_id}'  # W3C baggage format
}
```

**Viewing Costs in CloudWatch**:

1. **GenAI Observability Dashboard** (Agents Only):
   - Navigate to: [CloudWatch GenAI Observability](https://console.aws.amazon.com/cloudwatch/home#gen-ai-observability)
   - Select: Bedrock AgentCore tab
   - View: Agents View, Sessions View, Traces View
   - Filter by baggage attributes: `tenant_id`, `tier`, `clinic_id`
   - Metrics shown:
     - Session count and duration
     - Token usage (input/output)
     - Error rates
     - Latency percentiles

**Note**: Memory, Gateway, and Tool metrics are in CloudWatch Logs/Metrics, not GenAI Observability dashboard

2. **CloudWatch Logs Insights** (Memory Usage Per Tenant):

After enabling Memory observability, query tenant-specific memory usage:

```sql
-- Query Memory costs per tenant
-- Log group: /aws/vendedlogs/bedrock-agentcore/memory/APPLICATION_LOGS/{memory-id}
fields @timestamp, 
       baggage.tenant_id as tenant_id,
       baggage.clinic_id as clinic_id,
       baggage.actor_id as actor_id,
       operation,
       eventCount,
       retrievalCount,
       storageBytes
| filter ispresent(baggage.tenant_id)
| stats 
    sum(eventCount) as total_events,
    sum(retrievalCount) as total_retrievals,
    sum(storageBytes) as total_storage_bytes
  by tenant_id, clinic_id
| extend
    events_cost = total_events * 0.000001,
    retrievals_cost = total_retrievals * 0.000004,
    storage_cost = (total_storage_bytes / 1073741824) * 0.10,
    total_memory_cost = events_cost + retrievals_cost + storage_cost
| sort total_memory_cost desc
```

**Example Output**:
```
tenant_id        | clinic_id  | total_events | total_retrievals | total_memory_cost
-----------------|------------|--------------|------------------|------------------
basic-clinic-a   | clinic-a   | 10000        | 5000             | $0.03
premium-hospital-a| hospital-a| 15000        | 8000             | $0.047
```

3. **CloudWatch Logs Insights** (Runtime Costs Per Tenant):

```sql
# Query Runtime costs per tenant (from agent logs)
fields @timestamp, baggage.tenant_id as tenant_id, 
       baggage.tier as tier, baggage.clinic_id as clinic_id,
       duration_ms, memory_mb
| filter baggage.tenant_id like /clinic-/
| stats count() as invocations,
        sum(duration_ms)/1000 as total_seconds,
        avg(memory_mb) as avg_memory_mb
  by tenant_id, tier, clinic_id
| sort total_seconds desc
```

```sql
# Query Memory service costs per tenant
# Log group: /aws/vendedlogs/bedrock-agentcore/memory/APPLICATION_LOGS/{memory-id}
fields @timestamp, tenant_id, operation, 
       eventCount, retrievalCount
| filter tenant_id like /clinic-/
| stats sum(eventCount) as total_events,
        sum(retrievalCount) as total_retrievals
  by tenant_id
```

3. **CloudWatch Metrics** (Service-Provided):

Navigate to CloudWatch → Metrics → bedrock-agentcore namespace:
- **Runtime metrics**: Invocations, Duration, Errors
- **Memory metrics**: Events, Retrievals, Storage
- **Gateway metrics**: Requests, Latency
- **Tool metrics**: Invocations, Duration

Filter by dimension: `tenant_id`, `clinic_id` (from baggage)

## End-to-End Per-Tenant Cost Calculation Flow

### Visual Flow: Request to Cost Attribution

```
┌─────────────────────────────────────────────────────────────────────┐
│ 1. USER REQUEST                                                     │
│    Dr. Smith @ Clinic A: "Summarize this patient's lab results"    │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 2. API GATEWAY + LAMBDA PROXY                                       │
│    • Extracts JWT: custom:tenant_id=basic, custom:clinic_id=clinic-a│
│    • Adds to payload: {tenant_id: "basic", clinic_id: "clinic-a"}  │
│    • Routes to: basic-tier AgentCore runtime                        │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 3. AGENTCORE RUNTIME (main.py)                                      │
│    • Sets OpenTelemetry baggage:                                    │
│      - tenant_id = "basic-clinic-a"                                 │
│      - tier = "basic"                                               │
│      - clinic_id = "clinic-a"                                       │
│    • Baggage propagates to ALL subsequent operations                │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 4. OPERATIONS WITH AUTOMATIC COST TAGGING                           │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ Runtime Execution                                            │  │
│  │ • CPU: 2 seconds                                             │  │
│  │ • Memory: 512 MB                                             │  │
│  │ • Tagged: baggage.tenant_id = "basic-clinic-a"              │  │
│  │ → CloudWatch Logs: /aws/bedrock-agentcore/runtimes/...      │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ Memory Service                                               │  │
│  │ • Events: 5 new memories                                     │  │
│  │ • Retrievals: 10 memory lookups                              │  │
│  │ • Tagged: tenant_id = "basic-clinic-a" (from baggage)       │  │
│  │ → CloudWatch Logs: /aws/vendedlogs/.../memory/...           │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ Bedrock Model Invocation                                     │  │
│  │ • Model: us.amazon.nova-micro-v1:0                           │  │
│  │ • Inference Profile: healthcare-basic-clinic-a               │  │
│  │ • Profile Tags: ClinicID=clinic-a, Tier=basic               │  │
│  │ • Input: 1000 tokens, Output: 500 tokens                    │  │
│  │ → AWS Cost Explorer: Tagged with ClinicID                    │  │
│  └──────────────────────────────────────────────────────────────┘  │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 5. COST CALCULATION (End of Month)                                  │
│                                                                      │
│  Query 1: AWS Cost Explorer (Model Costs)                           │
│  ├─ Filter: Service=Bedrock, Tag:ClinicID=clinic-a                 │
│  └─ Result: $0.24 (1M input + 500K output tokens × Nova pricing)   │
│                                                                      │
│  Query 2: CloudWatch Logs (Runtime Costs)                           │
│  ├─ Filter: baggage.tenant_id="basic-clinic-a"                     │
│  └─ Result: $0.04 (3600 CPU-sec + 1800 GB-sec)                     │
│                                                                      │
│  Query 3: CloudWatch Logs (Memory Costs)                            │
│  ├─ Filter: tenant_id="basic-clinic-a"                             │
│  └─ Result: $0.03 (10K events + 5K retrievals)                     │
│                                                                      │
│  TOTAL FOR CLINIC A: $0.31                                          │
└─────────────────────────────────────────────────────────────────────┘
```

### Step-by-Step: How Costs Are Tracked Per Tenant

**1. Request Arrives with Tenant Context**
- User authenticates with Cognito (JWT contains `custom:clinic_id`)
- API Gateway validates and extracts tenant info
- Lambda proxy adds tenant context to payload

**2. Tenant Context Set in Code**
```python
# In main.py - Your code sets baggage (3 lines)
ctx = baggage.set_baggage("tenant_id", "basic-clinic-a")
ctx = baggage.set_baggage("tier", "basic")
ctx = baggage.set_baggage("clinic_id", "clinic-a")
context.attach(ctx)
```

**3. AgentCore Automatically Tags All Operations**
- Every span, metric, and log includes baggage
- Runtime invocations tagged with tenant_id
- Memory operations tagged with tenant_id
- Tool invocations tagged with tenant_id
- Model calls use clinic-specific inference profile with tags

**4. Costs Accumulate in Multiple Places**

| Cost Component | Where It's Tracked | How Tenant Is Identified |
|----------------|-------------------|-------------------------|
| **Model Costs** | AWS Cost Explorer | Inference profile tags: `ClinicID=clinic-a` |
| **Runtime CPU/Memory** | CloudWatch Logs | Baggage: `tenant_id=basic-clinic-a` |
| **Memory Events/Retrievals** | CloudWatch Logs | Baggage: `tenant_id=basic-clinic-a` |
| **Tool Usage** | CloudWatch Logs | Baggage: `tenant_id=basic-clinic-a` |
| **API Gateway** | CloudWatch Metrics | Usage plan: `basic-tier` |

**5. Monthly Cost Calculation Example**

**Clinic A (Basic Tier) - Monthly Usage:**

```python
# Data collected from CloudWatch and Cost Explorer
monthly_metrics = {
    # From CloudWatch Logs (Runtime)
    'runtime_cpu_seconds': 3600,      # 1 hour of CPU time
    'runtime_memory_gb_seconds': 1800, # 0.5 GB for 1 hour
    
    # From CloudWatch Logs (Memory service)
    'memory_events': 10000,
    'memory_retrievals': 5000,
    
    # From Cost Explorer (Bedrock model)
    'input_tokens': 1000000,          # 1M input tokens
    'output_tokens': 500000,          # 500K output tokens
    
    # From API Gateway metrics
    'api_requests': 5000
}

# Calculate costs
costs = {
    'runtime_cpu': 3600 * 0.000011,              # $0.0396
    'runtime_memory': 1800 * 0.0000012,          # $0.00216
    'memory_events': 10000 * 0.000001,           # $0.01
    'memory_retrievals': 5000 * 0.000004,        # $0.02
    'model_input': (1000000/1000) * 0.00008,     # $0.08 (Nova Micro)
    'model_output': (500000/1000) * 0.00032,     # $0.16 (Nova Micro)
    'api_gateway': 5000 * 0.0000035,             # $0.0175
}

total_cost = sum(costs.values())  # $0.329 for Clinic A
```

**Hospital A (Premium Tier) - Same Usage:**
```python
# Same metrics but different model pricing
costs = {
    'runtime_cpu': 3600 * 0.000011,              # $0.0396
    'runtime_memory': 1800 * 0.0000012,          # $0.00216
    'memory_events': 10000 * 0.000001,           # $0.01
    'memory_retrievals': 5000 * 0.000004,        # $0.02
    'model_input': (1000000/1000) * 0.003,       # $3.00 (Claude Sonnet 4.5)
    'model_output': (500000/1000) * 0.015,       # $7.50 (Claude Sonnet 4.5)
    'api_gateway': 5000 * 0.0000035,             # $0.0175
}

total_cost = sum(costs.values())  # $10.599 for Hospital A
```

**Key Insight**: Premium costs 32x more due to Claude Sonnet 4.5 pricing!

### Practical Steps to Calculate Per-Tenant Costs

**Step 1: Get Model Costs from Cost Explorer**

```bash
# Via AWS CLI
aws ce get-cost-and-usage \
  --time-period Start=2025-02-01,End=2025-03-01 \
  --granularity MONTHLY \
  --metrics "UnblendedCost" \
  --group-by Type=TAG,Key=ClinicID \
  --filter file://filter.json

# filter.json
{
  "Dimensions": {
    "Key": "SERVICE",
    "Values": ["Amazon Bedrock"]
  }
}
```

**Output:**
```json
{
  "ResultsByTime": [{
    "Groups": [
      {"Keys": ["ClinicID$clinic-a"], "Metrics": {"UnblendedCost": {"Amount": "0.24"}}},
      {"Keys": ["ClinicID$hospital-a"], "Metrics": {"UnblendedCost": {"Amount": "10.50"}}}
    ]
  }]
}
```

**Step 2: Get Runtime Costs from CloudWatch Logs**

```sql
-- CloudWatch Logs Insights Query
-- Log Group: /aws/bedrock-agentcore/runtimes/{agent-id}/runtime-logs

fields @timestamp, 
       baggage.tenant_id as tenant_id,
       baggage.clinic_id as clinic_id,
       duration as duration_ms,
       memory as memory_mb
| filter ispresent(baggage.tenant_id)
| stats 
    count() as invocations,
    sum(duration_ms)/1000 as total_cpu_seconds,
    avg(memory_mb)/1024 as avg_memory_gb,
    sum(duration_ms)/1000 * avg(memory_mb)/1024 as total_memory_gb_seconds
  by tenant_id, clinic_id
| extend 
    cpu_cost = total_cpu_seconds * 0.000011,
    memory_cost = total_memory_gb_seconds * 0.0000012,
    runtime_cost = cpu_cost + memory_cost
```

**Output:**
```
tenant_id        | clinic_id | invocations | cpu_cost | memory_cost | runtime_cost
-----------------|-----------|-------------|----------|-------------|-------------
basic-clinic-a   | clinic-a  | 150         | $0.0396  | $0.00216    | $0.04176
premium-hospital-a| hospital-a| 200         | $0.0528  | $0.00288    | $0.05568
```

**Step 3: Get Memory Costs from CloudWatch Logs**

```sql
-- CloudWatch Logs Insights Query
-- Log Group: /aws/vendedlogs/bedrock-agentcore/memory/APPLICATION_LOGS/{memory-id}

fields @timestamp,
       tenant_id,
       operation,
       eventCount,
       retrievalCount
| filter ispresent(tenant_id)
| stats 
    sum(eventCount) as total_events,
    sum(retrievalCount) as total_retrievals
  by tenant_id
| extend
    events_cost = total_events * 0.000001,
    retrievals_cost = total_retrievals * 0.000004,
    memory_cost = events_cost + retrievals_cost
```

**Output:**
```
tenant_id        | total_events | total_retrievals | memory_cost
-----------------|--------------|------------------|------------
basic-clinic-a   | 10000        | 5000             | $0.03
premium-hospital-a| 15000        | 8000             | $0.047
```

**Step 4: Combine All Costs**

```python
# Python script to generate final report
import boto3
from datetime import datetime, timedelta

def generate_tenant_cost_report(start_date, end_date):
    """Generate complete per-tenant cost report"""
    
    # 1. Get model costs from Cost Explorer
    ce = boto3.client('ce')
    model_costs = ce.get_cost_and_usage(
        TimePeriod={'Start': start_date, 'End': end_date},
        Granularity='MONTHLY',
        Metrics=['UnblendedCost'],
        GroupBy=[{'Type': 'TAG', 'Key': 'ClinicID'}],
        Filter={'Dimensions': {'Key': 'SERVICE', 'Values': ['Amazon Bedrock']}}
    )
    
    # 2. Get runtime costs from CloudWatch Logs Insights
    logs = boto3.client('logs')
    runtime_query = """
        fields baggage.clinic_id as clinic_id, duration, memory
        | stats sum(duration)/1000 * 0.000011 as cpu_cost,
                sum(duration)/1000 * avg(memory)/1024 * 0.0000012 as memory_cost
          by clinic_id
    """
    runtime_costs = logs.start_query(
        logGroupName='/aws/bedrock-agentcore/runtimes/*/runtime-logs',
        startTime=int(datetime.strptime(start_date, '%Y-%m-%d').timestamp()),
        endTime=int(datetime.strptime(end_date, '%Y-%m-%d').timestamp()),
        queryString=runtime_query
    )
    
    # 3. Combine and format report
    report = []
    for clinic in ['clinic-a', 'clinic-b', 'hospital-a']:
        report.append({
            'clinic_id': clinic,
            'model_cost': get_model_cost(model_costs, clinic),
            'runtime_cost': get_runtime_cost(runtime_costs, clinic),
            'memory_cost': get_memory_cost(logs, clinic, start_date, end_date),
            'total_cost': calculate_total(clinic)
        })
    
    return report

# Generate report
report = generate_tenant_cost_report('2025-02-01', '2025-03-01')
print_cost_report(report)
```

**Final Output:**
```
Per-Tenant Cost Report (February 2025)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Clinic ID    | Tier    | Model  | Runtime | Memory | Total
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
clinic-a     | basic   | $0.24  | $0.04   | $0.03  | $0.31
clinic-b     | basic   | $0.18  | $0.03   | $0.02  | $0.23
hospital-a   | premium | $10.50 | $0.06   | $0.05  | $10.61
clinic-e     | premium | $8.20  | $0.05   | $0.04  | $8.29
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total                                                | $19.44
```

### Key Takeaways

1. **Model costs dominate** (95%+ of total) - tracked via inference profile tags
2. **Runtime costs are minimal** (<5%) - tracked via OpenTelemetry baggage
3. **Memory costs are minimal** (<5%) - tracked via OpenTelemetry baggage
4. **Premium tier costs 30-40x more** due to Claude Sonnet 4.5 pricing
5. **All costs automatically attributed** to tenants via tags and baggage

**What's Automatically Provided by AgentCore**:

| Resource | Service-Provided Data | Available in GenAI Observability | Available in CloudWatch |
|----------|----------------------|----------------------------------|------------------------|
| **Agent (Runtime)** | Metrics, Spans, Traces | ✅ Yes | ✅ Yes |
| **Memory** | Metrics, Spans*, Logs* | ❌ No | ✅ Yes |
| **Gateway** | Metrics | ❌ No | ✅ Yes |
| **Tools** | Metrics | ❌ No | ✅ Yes |

\* Memory spans and logs require enablement via console or API

**Benefits**:
- ✅ Automatic cost attribution per tenant via baggage
- ✅ Minimal code changes (3 lines to set baggage)
- ✅ Real-time visibility in CloudWatch dashboards
- ✅ Granular tracking: Runtime, Memory, Tools, Models
- ✅ Query-able logs for custom cost reports
- ✅ ADOT SDK automatically configured for hosted agents


### Implementation Checklist (Practical Steps)

**Phase 1: Enhance Existing Infrastructure (1 week)**
- [ ] Update model IDs to Claude Sonnet 4.5 for premium tier
- [ ] Extend `create_inference_profiles.py` to create clinic-specific profiles with tags
- [ ] Add OpenTelemetry baggage in `main.py` and `main_premium.py` for tenant context (3 lines)
- [ ] Update agent classes to use clinic-specific profiles from SSM
- [ ] Add `custom:clinic_id` attribute to Cognito user pool
- [ ] **CRITICAL**: Enable Memory observability for both Memory resources:
  - [ ] Run `setup_memory_observability.py` script OR
  - [ ] Configure via AgentCore Console (see "Step 1: Enable Memory Observability" section)
  - [ ] Verify log groups created: `/aws/vendedlogs/bedrock-agentcore/memory/APPLICATION_LOGS/{memory-id}`
  - [ ] Verify traces enabled in X-Ray
- [ ] Test cost attribution in CloudWatch Logs and GenAI Observability dashboard

**Phase 2: Enable Cost Reporting (1 week)**
- [ ] Enable cost allocation tags in AWS Billing Console (ClinicID, Tier, Project)
- [ ] Wait 24 hours for tags to appear in Cost Explorer
- [ ] Create Cost Explorer report grouped by ClinicID tag
- [ ] Set up CloudWatch Logs Insights saved queries for quick cost lookups
- [ ] Export sample cost report to CSV for demo
- [ ] Document cost per clinic for demo presentation

**Phase 3: Optional Enhancements (Nice-to-Have)**
- [ ] ⚠️ **Not Required for Demo** - Cost Explorer is sufficient
- [ ] QuickSight dashboard (if advanced visualizations needed)
- [ ] Automated cost alerts per clinic using AWS Budgets
- [ ] Monthly cost report automation with Lambda

**Quick Win: Immediate Cost Visibility**

**What's Available Today (No Additional Setup)**:

1. **CloudWatch GenAI Observability** (Runtime Only):
   - ✅ Already enabled in your `.bedrock_agentcore.yaml`
   - View Runtime metrics per agent (CPU, memory, duration)
   - Filter by session to see per-request costs
   - Access: CloudWatch Console → GenAI Observability → Bedrock AgentCore
   - **Note**: Memory metrics NOT included here - requires separate setup

2. **AWS Cost Explorer** (Recommended for Demo):
   - ✅ View Bedrock costs by inference profile tags
   - Current tags: Project=CustomerSupport, Tier=Basic/Premium
   - Add ClinicID tag for per-clinic breakdown
   - Access: AWS Billing Console → Cost Explorer

3. **CloudWatch Logs Insights** (Runtime Only):
   - Query agent invocation logs for token usage
   - Calculate model costs from token counts
   - Group by tenant_id from request metadata
   - Access: CloudWatch Console → Logs → Insights

**What Requires Setup**:

4. **Memory Cost Tracking** (Requires One-Time Setup):
   - ⚠️ Must enable observability per Memory resource (see "Step 1: Enable Memory Observability")
   - After setup: Query memory logs for events, retrievals, storage
   - Log group: `/aws/vendedlogs/bedrock-agentcore/memory/APPLICATION_LOGS/{memory-id}`
   - Use CloudWatch Logs Insights to calculate per-tenant memory costs

### Per-Tenant Cost Reporting

**Primary Goal**: Track and report costs per clinic (tenant) for billing/chargeback

**Cost Components Per Tenant**:
1. **Model Costs**: Bedrock invocations (via tagged inference profiles)
2. **Runtime Costs**: CPU + Memory consumption (via observability baggage)
3. **Memory Costs**: Events + Retrievals (via observability baggage)
4. **Tool Costs**: Gateway, Browser, Code Interpreter (via observability baggage)
5. **API Gateway**: Request costs (via usage plans)

**Recommended Approach for Demo** (Built-in AWS Tools):

```sql
-- CloudWatch Logs Insights Query: Monthly Cost Per Tenant
fields @timestamp, tenant_id, clinic_id, tier,
       model_cost, runtime_cost, memory_cost, tool_cost
| filter tenant_id like /clinic-/ or tenant_id like /hospital-/
| stats 
    sum(model_cost) as total_model,
    sum(runtime_cost) as total_runtime,
    sum(memory_cost) as total_memory,
    sum(tool_cost) as total_tools,
    sum(model_cost + runtime_cost + memory_cost + tool_cost) as total_cost
  by tenant_id, clinic_id, tier
| sort total_cost desc
```

**Example Cost Explorer Output**:

View in AWS Console showing per-tenant costs:

```
Cost by ClinicID (Last 30 Days)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Clinic ID    | Tier    | Bedrock | Runtime | Memory | Total
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
clinic-a     | basic   | $5.20   | $0.08   | $0.03  | $5.31
clinic-b     | basic   | $3.80   | $0.05   | $0.02  | $3.87
hospital-a   | premium | $45.60  | $1.20   | $0.45  | $49.35
clinic-e     | premium | $32.40  | $0.90   | $0.30  | $35.10
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total                                              | $93.63
```