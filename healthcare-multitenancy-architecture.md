# Healthcare Multi-Tenant Clinical Document Processing Architecture

## Executive Summary

This document outlines the transformation of the existing AgentCore multi-tenancy project into a healthcare clinical document processing platform. The architecture demonstrates sophisticated multi-tenancy patterns with **tier-based service levels** and **multiple tenants per tier**, showcasing complete isolation and differentiated capabilities for clinical document analysis.

### Project Focus: Multi-Tenancy Demonstration (Not Production Healthcare)

This is a **demo project** designed to showcase AgentCore's multi-tenancy capabilities using a healthcare context. The feature set is intentionally streamlined to focus on demonstrating:

1. **Tenant Isolation**: Each clinic accesses only their documents
2. **Tier Differentiation**: Premium tier gets better models and higher limits
3. **Resource Allocation**: API throttling enforced per tier
4. **Scalability**: Multiple clinics per tier with independent configurations
5. **Cost Allocation**: Allocate agentcore runtime and memory costs to tenant 

**Core Features (Minimal Viable Set)**:
- Document search and retrieval (tenant isolation)
- Document summarization (model differentiation)
- Data extraction (capability differentiation)
- Multi-document analysis (premium-only feature)
- Retain short and long term memory by tenant/user

This streamlined approach allows rapid implementation while effectively demonstrating all key multi-tenancy patterns.

## Architecture Overview

### Multi-Tenancy Strategy

The system implements a **two-level multi-tenancy model**:

1. **Service Tiers**: Basic and Premium tiers with different capabilities 
2. **Tenant Isolation**: Multiple healthcare organizations (clinics) within each tier

```
Healthcare Document Processing Platform
├── Basic Tier (Primary Care Focus)
│   ├── Clinic A (Family Practice)
│   ├── Clinic B (Urgent Care)
│   ├── Clinic C (Pediatrics)
│   └── Clinic D (Internal Medicine)
└── Premium Tier (Specialty Care Focus)
    ├── Hospital A (Multi-specialty)
    ├── Clinic E (Cardiology)
    ├── Clinic F (Oncology)
    └── Hospital B (Academic Medical Center)
```

### Core Capabilities by Tier

The Premium tier provides a **superset** of Basic tier capabilities with enhanced features and performance.

#### Feature Comparison Matrix (Streamlined for Multi-Tenancy Demo)

| Feature Category | Basic Tier | Premium Tier | Multi-Tenancy Capability Demonstrated |
|-----------------|------------|--------------|--------------------------------------|
| **Document Search & Retrieval** | ✅ Basic search | ✅ Advanced search | **Tenant Isolation** - Each clinic sees only their documents |
| **Document Summarization** | ✅ Simple summaries | ✅ Detailed analysis | **Model Differentiation** - Nova Micro vs Claude Sonnet 4.5 quality |
| **Data Extraction** | ✅ Basic fields | ✅ Complex extraction | **Processing Capability** - Tier-based feature access |
| **Web Search Capability** | ❌ | ✅ | **Premium Feature** - Access to external medical research and guidelines | 
| **API Rate Limit (Demo)** | 0.5 req/sec | 2 req/sec | **Resource Allocation** - Tier-based throttling |
| **Burst Limit (Demo)** | 2 requests | 5 requests | **Quota Management** - Fair resource distribution |
| **Daily Quota (Demo)** | 5 requests | 20 requests | **Usage Tracking** - Per-tenant limits |
| **Model** | Nova Micro | Claude Sonnet 4.5 | **Cost Optimization** - Tier-appropriate models |

**Key Multi-Tenancy Demonstrations:**
1. 🔒 **Isolation**: Clinic A cannot access Clinic B's documents
2. 🎯 **Differentiation**: Premium gets better models and higher limits
3. 🚦 **Throttling**: Rate limits enforced per tenant and tier
4. 📊 **Cost Tracking**: Usage and costs monitored per clinic for billing/analytics
5. 🌐 **Premium Features**: Web search capability exclusive to premium tier

#### Basic Tier - Primary Care Document Processing
**Focus**: Demonstrate tenant isolation and basic processing capabilities

- **Document Types**: Patient intake forms, appointment notes, lab results
- **Core Capabilities** (Minimal for Demo):
  1. **Document Search**: Find documents by patient name, date, or keywords
  2. **Basic Summarization**: Generate simple summaries of clinical notes
  3. **Data Extraction**: Extract basic fields (patient name, date, medications)
  
- **Model**: Amazon Nova Micro (cost-optimized)
- **Response Time**: Standard (2-5 seconds)
- **API Rate Limits (Demo)**: 0.5 req/sec, 5 requests/day
- **Burst Capacity**: 2 requests

**Demo Scenarios**:
- "Find all documents for patient John Doe"
- "Summarize this appointment note"
- "Extract medications from this document"

#### Premium Tier - Advanced Clinical Analytics (Superset of Basic)
**Focus**: Demonstrate enhanced capabilities and resource allocation

- **Document Types**: All Basic documents **PLUS** diagnostic reports, imaging studies
- **Core Capabilities** (Extends Basic):
  1. ✅ **All Basic Features** (search, summarization, extraction)
  2. ➕ **Advanced Summarization**: Detailed clinical analysis with insights
  3. ➕ **Complex Data Extraction**: Extract structured data from complex reports
  4. ➕ **Multi-Document Analysis**: Compare and correlate across multiple documents
  
- **Model**: Claude Sonnet 4.5 (high-performance)
- **Response Time**: Priority (1-2 seconds)
- **API Rate Limits (Demo)**: 2 req/sec, 20 requests/day (4x Basic)
- **Burst Capacity**: 5 requests (2.5x Basic)

**Demo Scenarios**:
- "Analyze trends across this patient's last 5 lab results"
- "Compare these two diagnostic reports and highlight changes"
- "Extract all diagnostic codes and findings from this pathology report"

## Technical Architecture

### Document Storage Structure

```
s3://healthcare-documents/
├── basic-tier/
│   ├── clinic-a/
│   │   ├── patient-intake/
│   │   ├── appointment-notes/
│   │   ├── lab-results/
│   │   └── prescriptions/
│   ├── clinic-b/
│   │   └── [same structure]
│   └── clinic-c/
│       └── [same structure]
└── premium-tier/
    ├── hospital-a/
    │   ├── diagnostic-reports/
    │   ├── imaging-studies/
    │   ├── pathology-reports/
    │   ├── surgical-notes/
    │   └── specialist-consultations/
    ├── clinic-e/
    │   └── [specialty-specific documents]
    └── hospital-b/
        └── [academic medical documents]
```

### Tenant Identification and Routing

The system leverages the existing **Cognito JWT-based authentication** with enhanced custom claims to support multi-clinic tenancy.

#### Current JWT Structure (Extended)
```python
# Current JWT claims structure
{
  "cognito:username": "dr.smith@clinic-a.com",
  "custom:tenant_id": "basic",           # Tier level (basic/premium)
  "custom:clinic_id": "clinic-a",        # Clinic level identifier
  "custom:role": "physician",            # Optional: user role
  "email": "dr.smith@clinic-a.com",
  "exp": 1640995200
}
```

#### Enhanced Tenant Extraction (Building on Existing)
```python
def extract_tenant_info_from_jwt(token: str) -> dict:
    """Extract both tier and clinic info from JWT token - extends existing jwt_utils.py"""
    try:
        # Existing JWT parsing logic from jwt_utils.py
        parts = token.split('.')
        if len(parts) != 3:
            return _get_fallback_tenant_info()
            
        payload = parts[1]
        payload += '=' * (4 - len(payload) % 4)  # Add padding
        decoded_bytes = base64.urlsafe_b64decode(payload)
        claims = json.loads(decoded_bytes.decode('utf-8'))
        
        # Extract tier and clinic information
        tier = claims.get('custom:tenant_id', 'basic')  # Existing claim
        clinic_id = claims.get('custom:clinic_id', 'demo-clinic')  # New claim
        
        print(f"🔍 DEBUG: JWT claims - tier: {tier}, clinic: {clinic_id}")
        
        return {
            'tier': tier,
            'clinic_id': clinic_id,
            'tenant_key': f"{tier}-{clinic_id}",  # e.g., "basic-clinic-a"
            's3_prefix': f"{tier}-tier/{clinic_id}/",
            'username': claims.get('cognito:username'),
            'role': claims.get('custom:role', 'user')
        }
    except Exception as e:
        print(f"🔍 DEBUG: JWT parsing failed: {e}")
        return _get_fallback_tenant_info()

def _get_fallback_tenant_info():
    """Fallback tenant info when JWT parsing fails"""
    return {
        'tier': 'basic',
        'clinic_id': 'demo-clinic',
        'tenant_key': 'basic-demo-clinic',
        's3_prefix': 'basic-tier/demo-clinic/',
        'username': 'demo-user',
        'role': 'user'
    }

# Enhanced payload processing in main.py
def process_tenant_context(payload, headers):
    """Process tenant context from multiple sources"""
    
    # Primary: Extract from JWT token (existing flow)
    auth_header = headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        jwt_token = auth_header[7:]  # Remove 'Bearer ' prefix
        tenant_info = extract_tenant_info_from_jwt(jwt_token)
    else:
        # Fallback: payload-based (existing flow)
        tenant_info = {
            'tier': payload.get('tenant_id', 'basic'),
            'clinic_id': payload.get('clinic_id', 'demo-clinic'),
            'tenant_key': f"{payload.get('tenant_id', 'basic')}-{payload.get('clinic_id', 'demo-clinic')}",
            's3_prefix': f"{payload.get('tenant_id', 'basic')}-tier/{payload.get('clinic_id', 'demo-clinic')}/"
        }
    
    return tenant_info

# Inference profile mapping (unchanged)
inference_profiles = {
    "basic": "arn:aws:bedrock:us-east-1:ACCOUNT:application-inference-profile/BASIC_NOVA",
    "premium": "arn:aws:bedrock:us-east-1:ACCOUNT:application-inference-profile/PREMIUM_CLAUDE"
}
```

#### Cognito User Pool Configuration Options

**Single User Pool with Custom Attributes (Recommended)**
```bash
# Add custom attributes to existing Cognito User Pool
aws cognito-idp add-custom-attributes \
  --user-pool-id us-east-1_JlX0bKAgU \
  --custom-attributes Name=clinic_id,AttributeDataType=String,Required=true

# Users register with clinic selection
# JWT automatically includes custom:clinic_id claim
```


### Agent Configuration Structure

```
project/
├── main.py                           # Basic tier entrypoint
├── main_premium.py                   # Premium tier entrypoint
├── agent_config/                     # Basic tier shared configuration
│   ├── agent.py                     # Basic clinical document agent
│   ├── context.py                   # Tenant context management
│   ├── document_processor.py        # Basic document processing tools
│   └── clinic_router.py             # Clinic-specific routing
├── agent_config_premium/             # Premium tier shared configuration
│   ├── agent.py                     # Advanced clinical document agent
│   ├── context.py                   # Premium context management
│   ├── advanced_processor.py        # Advanced analytics tools
│   └── clinic_router.py             # Premium clinic routing
├── tools/                           # Shared clinical tools
│   ├── document_search.py           # S3 document search
│   ├── clinical_nlp.py              # Medical text processing
│   ├── data_extraction.py           # Structured data extraction
│   └── medical_coding.py            # ICD-10, CPT code extraction
└── frontend/
    ├── streamlit_app.py             # Enhanced chat interface
    ├── clinic_selector.py           # Clinic selection UI
    └── document_viewer.py           # Document display component
```

## Chat Interface and User Experience

### Tenant Authentication Flow (Cognito JWT-Based)

The system extends the existing Cognito OAuth2 authentication flow to support multi-clinic tenancy:

1. **Cognito Authentication**: User authenticates via existing OAuth2 flow with PKCE
2. **Enhanced JWT Claims**: JWT token includes both `custom:tenant_id` (tier) and `custom:clinic_id` (clinic)
3. **Automatic Context Detection**: System extracts tenant info from JWT claims using existing `jwt_utils.py`
4. **Document Scope**: Chat interface shows only that clinic's documents based on S3 prefix
5. **Capability Display**: UI adapts to show tier-appropriate features (Basic vs Premium)

#### Authentication Implementation (Building on Existing)
```python
# Enhanced context setting in main.py (extends existing flow)
@app.entrypoint
async def invoke(payload, context):
    # ... existing setup code ...
    
    if not CustomerSupportContext.get_gateway_token_ctx():
        gateway_token = await get_gateway_access_token()
        CustomerSupportContext.set_gateway_token_ctx(gateway_token)
        
        # Enhanced tenant extraction (replaces existing single tenant_id)
        tenant_info = process_tenant_context(payload, context.headers or {})
        
        print(f"🔍 DEBUG: Tenant info - {tenant_info}")
        
        # Set enhanced context
        CustomerSupportContext.set_tenant_id_ctx(tenant_info['tier'])  # Existing
        CustomerSupportContext.set_clinic_id_ctx(tenant_info['clinic_id'])  # New
        CustomerSupportContext.set_tenant_key_ctx(tenant_info['tenant_key'])  # New
        CustomerSupportContext.set_s3_prefix_ctx(tenant_info['s3_prefix'])  # New
    
    # ... rest of existing code ...
```

#### Frontend Authentication (Extends Existing Streamlit App)
```python
# Enhanced user claims processing in auth.py
def get_enhanced_user_claims(self):
    """Get user claims with clinic information"""
    tokens = self.get_tokens()
    if tokens:
        claims = jwt.decode(tokens["id_token"], options={"verify_signature": False})
        return {
            'username': claims.get('cognito:username'),
            'email': claims.get('email'),
            'tier': claims.get('custom:tenant_id', 'basic'),
            'clinic_id': claims.get('custom:clinic_id', 'demo-clinic'),
            'role': claims.get('custom:role', 'user'),
            'tenant_key': f"{claims.get('custom:tenant_id', 'basic')}-{claims.get('custom:clinic_id', 'demo-clinic')}"
        }
    return None

# Usage in Streamlit app
user_claims = auth_manager.get_enhanced_user_claims()
if user_claims:
    st.sidebar.write(f"**Clinic:** {user_claims['clinic_id'].title()}")
    st.sidebar.write(f"**Tier:** {user_claims['tier'].title()}")
    st.sidebar.write(f"**Role:** {user_claims['role'].title()}")
```

### Sample Chat Interactions (Streamlined for Demo)

#### Basic Tier - Clinic A (Family Practice)
**Demonstrates**: Tenant isolation, basic search, simple summarization

```
User: "Find documents for patient Sarah Johnson"
Agent: "Found 3 documents for Sarah Johnson in Clinic A:
1. Appointment Note - Oct 15, 2024
2. Lab Results - Oct 20, 2024  
3. Prescription Record - Oct 22, 2024
[Shows only Clinic A documents - tenant isolation]"

User: "Summarize the October 15 appointment note"
Agent: "Patient presented with seasonal allergies. Prescribed Claritin 10mg daily.
Follow-up in 2 weeks if symptoms persist.
[Basic summary using Nova Micro]"

User: "Extract medications from this document"
Agent: "Medications found:
- Claritin 10mg, once daily
- Lisinopril 20mg, once daily (existing)
[Simple field extraction]"
```

#### Premium Tier - Hospital A (Multi-specialty)
**Demonstrates**: Enhanced capabilities, multi-document analysis, better model

```
User: "Find all lab results for patient Sarah Johnson"
Agent: "Found 5 lab results for Sarah Johnson in Hospital A:
- Complete Blood Count (CBC) - Oct 1, Oct 15, Nov 1
- Metabolic Panel - Oct 1, Nov 1
[Shows only Hospital A documents - tenant isolation]"

User: "Analyze trends across these lab results"
Agent: "Lab Result Trend Analysis (Oct-Nov 2024):
- Hemoglobin: Stable at 13.5-13.8 g/dL (normal range)
- Glucose: Decreasing trend 110 → 98 mg/dL (improving)
- Creatinine: Stable at 0.9 mg/dL (normal kidney function)

Clinical Insight: Glucose improvement suggests effective diabetes management.
Recommend continuing current treatment plan.
[Advanced analysis using Claude 4.5 Sonnet - multi-document correlation]"

User: "Compare the Oct 1 and Nov 1 metabolic panels"
Agent: "Metabolic Panel Comparison:

Changes from Oct 1 → Nov 1:
✅ Glucose: 110 → 98 mg/dL (improved, -11%)
✅ HbA1c: 6.8% → 6.2% (improved diabetes control)
➡️ Electrolytes: All stable within normal range
➡️ Kidney function: Unchanged, normal

Summary: Significant improvement in glycemic control. Patient responding well to treatment.
[Complex extraction and comparison - premium feature]"
```

**Key Demo Takeaways**:
- Basic tier: Simple queries, basic responses
- Premium tier: Complex analysis, multi-document insights
- Both tiers: Complete tenant isolation (each clinic sees only their data)

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

#### 2. Request Metadata (Granular Tracking)

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
**Current Status**: ✅ Already enabled in your `.bedrock_agentcore.yaml`

**How It Works**:

AgentCore Observability automatically tracks:
- **Runtime Costs**: CPU and memory consumption per agent invocation
- **Memory Costs**: Short-term memory events and long-term memory retrievals
- **Tool Costs**: Gateway, Browser, Code Interpreter usage
- **Session Metrics**: Duration, token usage, error rates

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

AgentCore automatically instruments your code when observability is enabled. You just need to add tenant context via OpenTelemetry baggage:

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
    context.attach(ctx)
    
    # All subsequent operations will include this tenant context
    # AgentCore automatically tags Runtime, Memory, and Tool costs with baggage
    response = await agent_task(...)
    return response
```

**How It Works**:
1. ✅ **Observability already enabled** in your `.bedrock_agentcore.yaml`
2. ✅ **ADOT SDK automatically configured** by AgentCore runtime
3. ✅ **Baggage propagates** to all spans, metrics, and logs
4. ✅ **CloudWatch receives** tenant-tagged telemetry automatically
5. ✅ **No additional configuration** needed for hosted agents

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

2. **CloudWatch Logs Insights** (All Resources):

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

### Cost Tracking Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Clinic A Request                         │
│  (JWT: custom:tenant_id=basic, custom:clinic_id=clinic-a)  │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              API Gateway + Lambda Proxy                      │
│  • Extracts tenant info from JWT                            │
│  • Adds to payload: {tenant_id, clinic_id}                  │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              AgentCore Runtime (Basic Tier)                  │
│  • Observability: tenant_id=clinic-a in all spans           │
│  • Memory: Tagged with clinic-a context                     │
│  • Runtime costs: Attributed via observability tags         │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              Bedrock Model Invocation                        │
│  • Application Inference Profile: clinic-a-profile          │
│  • Request Metadata: {tenantId: clinic-a, tier: basic}     │
│  • Model costs: Attributed via profile tags                 │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              Cost Tracking & Analytics                       │
│  ├─ AWS Cost Explorer: Profile tags → per-clinic costs     │
│  ├─ CloudWatch Logs: Request metadata → usage analytics    │
│  ├─ CloudWatch Observability: Runtime/Memory costs         │
│  └─ QuickSight: Custom dashboards per clinic               │
└─────────────────────────────────────────────────────────────┘
```

### Implementation Checklist (Practical Steps)

**Phase 1: Enhance Existing Infrastructure (1 week)**
- [ ] Update model IDs to Claude Sonnet 4.5 for premium tier
- [ ] Extend `create_inference_profiles.py` to create clinic-specific profiles with tags
- [ ] Add OpenTelemetry baggage in `main.py` and `main_premium.py` for tenant context (3 lines)
- [ ] Update agent classes to use clinic-specific profiles from SSM
- [ ] Add `custom:clinic_id` attribute to Cognito user pool
- [ ] Enable Memory observability (if using Memory service) via console or API
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

Without any code changes, you can see costs today:

1. **CloudWatch GenAI Observability**:
   - ✅ Already enabled in your `.bedrock_agentcore.yaml`
   - View Runtime/Memory metrics per agent
   - Filter by session to see per-request costs
   - Access: CloudWatch Console → GenAI Observability → Bedrock AgentCore

2. **AWS Cost Explorer** (Recommended for Demo):
   - ✅ View Bedrock costs by inference profile tags
   - Current tags: Project=CustomerSupport, Tier=Basic/Premium
   - Add ClinicID tag for per-clinic breakdown
   - Access: AWS Billing Console → Cost Explorer

3. **CloudWatch Logs Insights**:
   - Query invocation logs for token usage
   - Calculate model costs from token counts
   - Group by tenant_id from request metadata
   - Access: CloudWatch Console → Logs → Insights

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

**Key Insights for Demo**:
- Clear cost difference: Basic ($4.50 avg) vs Premium ($42.00 avg)
- Complete tenant isolation in billing
- Easy to generate chargeback reports

**1. AWS Cost Explorer** (Recommended for Demo):

Steps:
1. Enable cost allocation tags in AWS Billing Console:
   - `ClinicID`
   - `Tier`
   - `Project`

2. Create Cost Explorer report:
   - Group by: Tag → ClinicID
   - Filter: Service → Bedrock, AgentCore Runtime, AgentCore Memory
   - Time range: Last 30 days
   - View: Daily or Monthly costs

3. Export to CSV for billing:
```csv
ClinicID,Tier,BedrockCost,RuntimeCost,MemoryCost,TotalCost
clinic-a,basic,$5.20,$0.08,$0.03,$5.31
clinic-b,basic,$3.80,$0.05,$0.02,$3.87
hospital-a,premium,$45.60,$1.20,$0.45,$49.35
```

**Benefits**: 
- ✅ No custom development needed
- ✅ Built-in AWS tool
- ✅ Perfect for demo purposes
- ✅ Real-time cost data

**2. CloudWatch Logs Insights** (Quick Queries):

```sql
# Simple per-tenant cost query
fields @timestamp, tenant_id, clinic_id, 
       sum(model_tokens * token_cost) as model_cost
| filter tenant_id like /clinic-/
| stats sum(model_cost) by clinic_id
| sort sum(model_cost) desc
```

**Benefits**:
- ✅ Quick ad-hoc queries
- ✅ No infrastructure setup
- ✅ Good for troubleshooting

**3. QuickSight Dashboard** (Nice-to-Have, Optional):

⚠️ **Not required for demo** - Cost Explorer is sufficient

If you want advanced visualizations:
- Create QuickSight dataset from CloudWatch Logs
- Build interactive dashboards with drill-downs
- Add cost trend charts and forecasting

**Effort**: 1-2 weeks additional work  
**Value for Demo**: Low - Cost Explorer already shows per-tenant costs

### Cost Optimization Strategies

1. **Tier-Appropriate Models**: Basic uses Nova Micro, Premium uses Claude Sonnet 4.5
2. **Memory Management**: Separate memory instances per clinic
3. **Rate Limiting**: Prevent runaway costs via API throttling
4. **Usage Monitoring**: Real-time alerts on cost anomalies
5. **Resource Tagging**: Consistent tagging for accurate attribution

### Summary: Complete Per-Tenant Cost Tracking

**Your Current Setup** (Already Good!):
- ✅ Inference profiles with tier-level tags
- ✅ AgentCore observability enabled
- ✅ JWT-based tenant identification
- ✅ Separate agents per tier

## AgentCore Memory Isolation Strategy

**CRITICAL REQUIREMENT**: Proper memory isolation is essential for multi-tenant healthcare applications to ensure complete data separation between clinics and users.

### Two-Level Memory Isolation Architecture

AgentCore Memory provides isolation through **`actor_id`** and **namespace templates**, enabling a single Memory resource to serve multiple tenants with complete data separation.

**Isolation Levels**:
1. **Clinic-Level Isolation**: Each clinic's data is isolated via namespace prefixes
2. **User-Level Isolation**: Each user within a clinic is isolated via unique `actor_id`

### Implementation Approach: Single Memory Resource with Namespace Isolation (Recommended)

Use one Memory resource per tier with namespace templates for automatic isolation:

```python
# Memory resource configuration (one per tier)
from bedrock_agentcore.memory import MemoryClient

client = MemoryClient(region_name="us-east-1")

# Basic tier memory
memory_basic = client.create_memory_and_wait(
    name="healthcare-basic-memory",
    strategies=[
        {
            "semanticMemoryStrategy": {
                "name": "clinical-facts",
                "description": "Clinical facts and patient information",
                "namespaces": [
                    "clinic/{actorId}/facts/{sessionId}",  # Clinic + user isolation
                    "clinic/{actorId}/preferences"          # User preferences
                ]
            }
        }
    ],
    event_expiry_days=90
)

# Premium tier memory
memory_premium = client.create_memory_and_wait(
    name="healthcare-premium-memory",
    strategies=[
        {
            "semanticMemoryStrategy": {
                "name": "clinical-insights",
                "description": "Advanced clinical insights and analytics",
                "namespaces": [
                    "clinic/{actorId}/insights/{sessionId}",
                    "clinic/{actorId}/preferences",
                    "clinic/{actorId}/analytics"  # Premium-only namespace
                ]
            }
        }
    ],
    event_expiry_days=180  # Longer retention for premium
)
```

### How Isolation Works

**Actor ID Format** (Critical for Isolation):

```python
# Each user gets a unique actor_id combining tier, clinic, and user
# Format: "{tier}-{clinic_id}-{user_id}"

# Examples:
actor_id_user1_clinic_a = "basic-clinic-a-dr-smith"
actor_id_user2_clinic_a = "basic-clinic-a-dr-jones"
actor_id_user1_clinic_b = "basic-clinic-b-dr-wilson"
actor_id_user1_hospital_a = "premium-hospital-a-dr-chen"
```

**Storing Isolated Events**:

```python
from bedrock_agentcore.memory import MemorySessionManager, ConversationalMessage, MessageRole

# Initialize manager with tier-specific memory
manager = MemorySessionManager(
    memory_id=memory_basic["memoryId"],
    region_name="us-east-1"
)

# Dr. Smith's conversation (Clinic A) - Isolated by actor_id
manager.add_turns(
    actor_id="basic-clinic-a-dr-smith",  # Unique per user
    session_id="session-123",
    messages=[
        ConversationalMessage("Patient has diabetes", MessageRole.USER),
        ConversationalMessage("Noted. Reviewing treatment options.", MessageRole.ASSISTANT)
    ]
)

# Dr. Jones's conversation (Clinic A) - COMPLETELY ISOLATED from Dr. Smith
manager.add_turns(
    actor_id="basic-clinic-a-dr-jones",  # Different actor_id = different memory
    session_id="session-456",
    messages=[
        ConversationalMessage("Patient has hypertension", MessageRole.USER),
        ConversationalMessage("Understood. Checking guidelines.", MessageRole.ASSISTANT)
    ]
)

# Dr. Wilson's conversation (Clinic B) - ISOLATED FROM CLINIC A
manager.add_turns(
    actor_id="basic-clinic-b-dr-wilson",
    session_id="session-789",
    messages=[
        ConversationalMessage("Patient needs cardiology referral", MessageRole.USER),
        ConversationalMessage("I'll prepare the referral documentation.", MessageRole.ASSISTANT)
    ]
)
```

**Namespace Resolution** (Automatic by AgentCore):

```python
# Template: "clinic/{actorId}/facts/{sessionId}"
# For actor_id="basic-clinic-a-dr-smith", session_id="session-123"
# Resolves to: "clinic/basic-clinic-a-dr-smith/facts/session-123"

# This means:
# - Dr. Smith can ONLY access memories in "clinic/basic-clinic-a-dr-smith/*"
# - Dr. Jones can ONLY access memories in "clinic/basic-clinic-a-dr-jones/*"
# - Dr. Wilson can ONLY access memories in "clinic/basic-clinic-b-dr-wilson/*"
# - NO cross-user or cross-clinic access possible
```

**Retrieving Isolated Memories**:

```python
# Dr. Smith retrieves their own memories
memories = manager.search_long_term_memories(
    query="diabetes treatment",
    namespace_prefix="clinic/basic-clinic-a-dr-smith/facts",  # Only their namespace
    top_k=5
)
# Returns: Only Dr. Smith's diabetes-related memories

# Dr. Smith CANNOT access Dr. Jones's memories
# This would return empty results:
memories = manager.search_long_term_memories(
    query="hypertension",  # Dr. Jones's topic
    namespace_prefix="clinic/basic-clinic-a-dr-jones/facts",  # Different actor's namespace
    top_k=5
)
# Returns: [] (no access to other actor's data)

# Cross-clinic access also fails
memories = manager.search_long_term_memories(
    query="cardiology",  # Dr. Wilson's topic (Clinic B)
    namespace_prefix="clinic/basic-clinic-b-dr-wilson/facts",
    top_k=5
)
# Returns: [] (no cross-clinic access)
```

### Enhanced Tenant Context Extraction

Update JWT parsing to include user-level identification:

```python
# In agent_config/jwt_utils.py
import base64
import json
import logging

logger = logging.getLogger(__name__)

def extract_tenant_info_from_jwt(token: str) -> dict:
    """Extract tier, clinic, and user info from JWT token for complete isolation"""
    try:
        parts = token.split('.')
        if len(parts) != 3:
            logger.warning("Invalid JWT format, using fallback")
            return _get_fallback_tenant_info()
            
        payload = parts[1]
        payload += '=' * (4 - len(payload) % 4)  # Add padding
        decoded_bytes = base64.urlsafe_b64decode(payload)
        claims = json.loads(decoded_bytes.decode('utf-8'))
        
        # Extract all levels of identification
        tier = claims.get('custom:tenant_id', 'basic')
        clinic_id = claims.get('custom:clinic_id', 'demo-clinic')
        user_id = claims.get('cognito:username', 'demo-user')
        
        # Construct hierarchical actor_id for complete isolation
        # Format: "{tier}-{clinic_id}-{user_id}"
        actor_id = f"{tier}-{clinic_id}-{user_id}"
        
        logger.info(f"Extracted tenant info - Tier: {tier}, Clinic: {clinic_id}, User: {user_id}")
        logger.info(f"Generated actor_id: {actor_id}")
        
        return {
            'tier': tier,
            'clinic_id': clinic_id,
            'user_id': user_id,
            'actor_id': actor_id,  # CRITICAL: Unique per user for memory isolation
            'memory_id': f"healthcare-{tier}-memory",
            's3_prefix': f"{tier}-tier/{clinic_id}/",
            'inference_profile': f"healthcare-{tier}-{clinic_id}"
        }
    except Exception as e:
        logger.error(f"JWT parsing failed: {e}")
        return _get_fallback_tenant_info()

def _get_fallback_tenant_info():
    """Fallback tenant info when JWT parsing fails"""
    return {
        'tier': 'basic',
        'clinic_id': 'demo-clinic',
        'user_id': 'demo-user',
        'actor_id': 'basic-demo-clinic-demo-user',
        'memory_id': 'healthcare-basic-memory',
        's3_prefix': 'basic-tier/demo-clinic/',
        'inference_profile': 'healthcare-basic-demo-clinic'
    }
```

### Agent Integration with Memory Isolation

```python
# In main.py and main_premium.py
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from bedrock_agentcore.memory import MemorySessionManager
from agent_config.jwt_utils import extract_tenant_info_from_jwt

app = BedrockAgentCoreApp()

@app.entrypoint
async def invoke(payload, context):
    # Extract tenant info including user-specific actor_id
    auth_header = context.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        jwt_token = auth_header[7:]
        tenant_info = extract_tenant_info_from_jwt(jwt_token)
    else:
        tenant_info = {
            'tier': payload.get('tenant_id', 'basic'),
            'clinic_id': payload.get('clinic_id', 'demo-clinic'),
            'user_id': payload.get('user_id', 'demo-user'),
            'actor_id': f"{payload.get('tenant_id', 'basic')}-{payload.get('clinic_id', 'demo-clinic')}-{payload.get('user_id', 'demo-user')}",
            'memory_id': f"healthcare-{payload.get('tenant_id', 'basic')}-memory"
        }
    
    # Initialize memory manager with tier-specific memory
    memory_manager = MemorySessionManager(
        memory_id=tenant_info['memory_id'],  # "healthcare-basic-memory" or "healthcare-premium-memory"
        region_name="us-east-1"
    )
    
    # Create session with user-specific actor_id for complete isolation
    session = memory_manager.create_memory_session(
        actor_id=tenant_info['actor_id'],  # e.g., "basic-clinic-a-dr-smith"
        session_id=context.session_id
    )
    
    # All memory operations are now automatically isolated per user
    # - Short-term memory (events) isolated by actor_id
    # - Long-term memory (semantic) isolated by namespace templates
    
    # Process user request with isolated memory
    user_input = payload.get('prompt', '')
    
    # Retrieve relevant memories (automatically isolated to this user)
    from bedrock_agentcore.memory.constants import RetrievalConfig
    
    retrieval_config = {
        f"clinic/{tenant_info['actor_id']}/facts/{{sessionId}}": RetrievalConfig(
            top_k=5,
            relevance_score=0.3
        )
    }
    
    # Process with LLM (memories are automatically filtered to this user)
    memories, response, event = session.process_turn_with_llm(
        user_input=user_input,
        llm_callback=my_llm_function,
        retrieval_config=retrieval_config
    )
    
    return {"response": response}
```


### Security Guarantees

AgentCore Memory provides these isolation guarantees at the **API level**:

1. **Actor Isolation**: Events and memories with different `actor_id` values are completely isolated
2. **Namespace Isolation**: Template variables `{actorId}` ensure automatic namespace separation
3. **API-Level Enforcement**: AgentCore APIs enforce isolation at the service level (not application level)
4. **No Cross-Actor Access**: There is no API to list or access another actor's data
5. **Immutable actor_id**: Once an event is created with an `actor_id`, it cannot be accessed by other actors

**From AgentCore Documentation**:
> "The `actor_id` parameter provides complete isolation between different actors. Events, short-term memory, and long-term memory records are scoped to the specific `actor_id` and cannot be accessed by other actors."

### Cost Implications

**Single Memory Approach** (Recommended):
- Memory resource cost: ~$0.10/GB-month for long-term storage
- Event storage: $0.000001 per event
- Retrieval: $0.000004 per call
- **Total for 8 clinics**: Cost of 2 Memory resources (basic + premium)
- **Example**: $0.20/GB-month total for both tiers


### Implementation Checklist

**Phase 1: Memory Resource Setup**
- [ ] Create 2 Memory resources (basic-tier, premium-tier) with namespace templates
- [ ] Configure namespace templates: `"clinic/{actorId}/facts/{sessionId}"`
- [ ] Store Memory resource IDs in SSM:
  - `/app/healthcare/memory/basic_id`
  - `/app/healthcare/memory/premium_id`
- [ ] Verify Memory resources are ACTIVE

**Phase 2: JWT and Actor ID Configuration**
- [ ] Update JWT parsing to extract `user_id` from `cognito:username`
- [ ] Implement hierarchical `actor_id` construction: `"{tier}-{clinic_id}-{user_id}"`
- [ ] Update agent code to use user-specific `actor_id` for all memory operations
- [ ] Add logging for `actor_id` generation for debugging

**Phase 3: Agent Integration**
- [ ] Update `main.py` to initialize `MemorySessionManager` with tier-specific memory
- [ ] Update `main_premium.py` similarly
- [ ] Configure `retrieval_config` with namespace templates
- [ ] Test memory operations with different `actor_id` values

**Phase 4: Isolation Testing**
- [ ] Test same-user access (should succeed)
- [ ] Test cross-user access within same clinic (should fail - return empty)
- [ ] Test cross-clinic access (should fail - return empty)
- [ ] Test cross-tier access (should fail - different Memory resources)
- [ ] Document test results

**Phase 5: Monitoring and Observability**
- [ ] Configure CloudWatch alarms for memory usage per tier
- [ ] Set up cost tracking for Memory service
- [ ] Add `actor_id` to observability baggage for cost attribution
- [ ] Create dashboard showing memory usage by clinic

**Phase 6: Documentation**
- [ ] Document `actor_id` format: `"{tier}-{clinic_id}-{user_id}"`
- [ ] Document namespace template patterns
- [ ] Create runbook for adding new clinics (no infrastructure changes needed)
- [ ] Document isolation verification procedures

**What to Add for Clinic-Level Tracking**:
1. **Clinic-specific inference profiles** (extend existing script)
2. **OpenTelemetry baggage** (add 3 lines to main.py)
3. **Cost allocation tags** (enable in AWS Billing Console)

**Result**: Complete cost visibility per clinic
- Model costs: Tagged inference profiles → Cost Explorer
- Runtime costs: Observability baggage → CloudWatch Logs
- Memory costs: Observability baggage → CloudWatch Logs
- Simple reporting: CloudWatch Logs Insights + Cost Explorer

**Demo Value**:
- Show cost differences: Basic ($5/month) vs Premium ($45/month)
- Demonstrate tenant isolation: Clinic A can't see Clinic B's costs
- Prove scalability: Add new clinic = new profile + automatic tracking

### References

- [Cost tracking multi-tenant model inference on Amazon Bedrock](https://aws.amazon.com/blogs/machine-learning/cost-tracking-multi-tenant-model-inference-on-amazon-bedrock/)
- [Manage multi-tenant Amazon Bedrock costs using application inference profiles](https://aws.amazon.com/blogs/machine-learning/manage-multi-tenant-amazon-bedrock-costs-using-application-inference-profiles/)
- [Amazon Bedrock AgentCore Pricing](https://aws.amazon.com/bedrock/agentcore/pricing/)
- [AgentCore Observability Documentation](https://aws.github.io/bedrock-agentcore-starter-toolkit/user-guide/observability/quickstart.md)

## API Gateway Configuration (Existing Infrastructure)

The project already has a comprehensive API Gateway setup with tenant-based throttling. Here's what exists and what needs enhancement for healthcare multi-clinic use:

### ✅ Existing API Gateway Infrastructure

**CloudFormation Template**: `prerequisite/api_gateway_template.yaml`
- REST API Gateway with Lambda proxy integration
- Usage plans for Basic and Premium tiers
- API keys for tenant authentication
- Tenant routing via Lambda proxy

**Current Usage Plans** (Demo Configuration):
```yaml
BasicUsagePlan:
  RateLimit: 0.5 req/sec (1 request per 2 seconds)
  BurstLimit: 2 requests
  Quota: 5 requests per day

PremiumUsagePlan:
  RateLimit: 2 req/sec
  BurstLimit: 5 requests
  Quota: 20 requests per day
```

**Lambda Proxy Handler**: `prerequisite/lambda/python/api_gateway_lambda.py`
- Extracts tenant_id from JWT claims (`custom:tenant_id`)
- Routes to appropriate AgentCore runtime (basic vs premium)
- Adds tenant_id to payload for downstream processing
- Forwards requests to AgentCore with proper authentication

### 🔧 Required Enhancements for Healthcare Multi-Clinic

#### 1. Keep Existing Demo Usage Plans (No Changes Needed)
```yaml
# Current demo limits in api_gateway_template.yaml are appropriate for demo
BasicUsagePlan:
  RateLimit: 0.5 req/sec         # 1 request per 2 seconds
  BurstLimit: 2 requests
  Quota: 5 requests per day      # Easy to hit for demo purposes

PremiumUsagePlan:
  RateLimit: 2 req/sec           # 4x faster than basic
  BurstLimit: 5 requests         # 2.5x more burst capacity
  Quota: 20 requests per day     # 4x more daily quota

# These limits clearly demonstrate tier differentiation in demos
```

#### 2. Enhance Lambda Proxy for Clinic-Level Routing
```python
# Update api_gateway_lambda.py to extract clinic_id
def extract_tenant_info(event: Dict[str, Any]) -> Dict[str, str]:
    """Extract both tier and clinic info from JWT"""
    request_context = event.get('requestContext', {})
    authorizer = request_context.get('authorizer', {})
    claims = authorizer.get('claims', {})
    
    tier = claims.get('custom:tenant_id', 'basic')
    clinic_id = claims.get('custom:clinic_id', 'demo-clinic')  # NEW
    
    return {
        'tier': tier,
        'clinic_id': clinic_id,
        'tenant_key': f"{tier}-{clinic_id}",
        's3_prefix': f"{tier}-tier/{clinic_id}/"
    }

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    # Extract enhanced tenant info
    tenant_info = extract_tenant_info(event)
    
    # Add both tier and clinic_id to payload
    body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
    body['tenant_id'] = tenant_info['tier']
    body['clinic_id'] = tenant_info['clinic_id']  # NEW
    
    # Route to appropriate agent based on tier
    if tenant_info['tier'] == "premium":
        agent_arn = get_premium_agent_arn()
    else:
        agent_arn = get_basic_agent_arn()
    
    # Forward with enhanced context
    response = forward_to_agentcore(
        agent_arn=agent_arn,
        payload=json.dumps(body),
        session_id=session_id,
        bearer_token=bearer_token
    )
    
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'text/plain',
            'X-Tenant-ID': tenant_info['tier'],
            'X-Clinic-ID': tenant_info['clinic_id'],  # NEW
            'X-RateLimit-Limit': get_rate_limit(tenant_info['tier'])
        },
        'body': response
    }
```

#### 3. Add Per-Clinic API Keys (Optional)
```yaml
# For clinic-specific API keys (if needed)
ClinicAApiKey:
  Type: AWS::ApiGateway::ApiKey
  Properties:
    Name: clinic-a-api-key
    Description: API Key for Clinic A (Basic Tier)
    Enabled: true

HospitalAApiKey:
  Type: AWS::ApiGateway::ApiKey
  Properties:
    Name: hospital-a-api-key
    Description: API Key for Hospital A (Premium Tier)
    Enabled: true
```

### Deployment
```bash
# Deploy/update API Gateway stack
cd agentcore-and-multitenancy/scripts
./deploy_api_gateway.sh

# Get API Gateway URL and API keys
aws cloudformation describe-stacks \
  --stack-name agentcore-multitenant-api \
  --query 'Stacks[0].Outputs'
```

## Implementation Gaps and Requirements

### Current State Assessment

#### ✅ **Existing Capabilities (Leveraged)**
- ✅ Multi-tenant agent architecture with tier separation (basic/premium)
- ✅ JWT-based authentication with Cognito (custom:tenant_id)
- ✅ AgentCore runtime with session management
- ✅ AgentCore observability enabled for cost tracking
- ✅ Streamlit chat interface foundation
- ✅ SSM parameter store configuration
- ✅ Memory management and conversation persistence
- ✅ Inference profiles with tier-level tags
- ✅ API Gateway with usage plans and throttling
- ✅ Lambda proxy for tenant routing

#### 🔧 **Enhancements Needed (Building on Existing)**
- 🔧 Add `custom:clinic_id` to JWT claims (extends existing auth)
- 🔧 Create clinic-specific inference profiles (extends existing script)
- 🔧 Add OpenTelemetry baggage for cost attribution (3 lines of code)
- 🔧 Update to Claude Sonnet 4.5 for premium tier (model ID change)
- 🔧 Enable cost allocation tags in AWS Billing Console (one-time setup)

#### ❌ **New Implementations Required**

### 1. **AgentCore Memory Isolation (CRITICAL)**
**Gap**: Current system lacks proper user-level memory isolation within clinics
**Priority**: 🔴 **CRITICAL** - Required for multi-tenant security and data privacy
**Current Status**: ❌ No memory isolation implementation
**Requirements**:
- Create 2 Memory resources (basic-tier, premium-tier) with namespace templates
- Implement user-specific `actor_id` for complete isolation: `"{tier}-{clinic_id}-{user_id}"`
- Configure namespace templates: `"clinic/{actorId}/facts/{sessionId}"`
- Update JWT parsing to extract `user_id` from `cognito:username`
- Integrate `MemorySessionManager` with user-specific `actor_id` in agent code
- Test and verify cross-user and cross-clinic isolation

**Implementation Needed**:
```python
# 1. Create Memory Resources (one-time setup)
from bedrock_agentcore.memory import MemoryClient

client = MemoryClient(region_name="us-east-1")

# Basic tier memory with namespace templates
memory_basic = client.create_memory_and_wait(
    name="healthcare-basic-memory",
    strategies=[
        {
            "semanticMemoryStrategy": {
                "name": "clinical-facts",
                "description": "Clinical facts and patient information",
                "namespaces": [
                    "clinic/{actorId}/facts/{sessionId}",  # Auto-isolates by actor_id
                    "clinic/{actorId}/preferences"
                ]
            }
        }
    ],
    event_expiry_days=90
)

# Premium tier memory with additional namespaces
memory_premium = client.create_memory_and_wait(
    name="healthcare-premium-memory",
    strategies=[
        {
            "semanticMemoryStrategy": {
                "name": "clinical-insights",
                "description": "Advanced clinical insights",
                "namespaces": [
                    "clinic/{actorId}/insights/{sessionId}",
                    "clinic/{actorId}/preferences",
                    "clinic/{actorId}/analytics"  # Premium-only
                ]
            }
        }
    ],
    event_expiry_days=180
)

# Store Memory IDs in SSM
import boto3
ssm = boto3.client('ssm')
ssm.put_parameter(
    Name='/app/healthcare/memory/basic_id',
    Value=memory_basic['memoryId'],
    Type='String',
    Overwrite=True
)
ssm.put_parameter(
    Name='/app/healthcare/memory/premium_id',
    Value=memory_premium['memoryId'],
    Type='String',
    Overwrite=True
)
```

```python
# 2. Update JWT parsing to construct user-specific actor_id
# In agent_config/jwt_utils.py
def extract_tenant_info_from_jwt(token: str) -> dict:
    """Extract tier, clinic, and user info for memory isolation"""
    try:
        # ... existing JWT parsing ...
        
        tier = claims.get('custom:tenant_id', 'basic')
        clinic_id = claims.get('custom:clinic_id', 'demo-clinic')
        user_id = claims.get('cognito:username', 'demo-user')
        
        # CRITICAL: Construct hierarchical actor_id for complete isolation
        actor_id = f"{tier}-{clinic_id}-{user_id}"
        
        return {
            'tier': tier,
            'clinic_id': clinic_id,
            'user_id': user_id,
            'actor_id': actor_id,  # e.g., "basic-clinic-a-dr-smith"
            'memory_id': f"healthcare-{tier}-memory",
            's3_prefix': f"{tier}-tier/{clinic_id}/"
        }
    except Exception as e:
        logger.error(f"JWT parsing failed: {e}")
        return _get_fallback_tenant_info()
```

```python
# 3. Integrate MemorySessionManager in agent code
# In main.py and main_premium.py
from bedrock_agentcore.memory import MemorySessionManager
from agent_config.jwt_utils import extract_tenant_info_from_jwt

@app.entrypoint
async def invoke(payload, context):
    # Extract tenant info with user-specific actor_id
    tenant_info = extract_tenant_info_from_jwt(jwt_token)
    
    # Initialize memory manager with tier-specific memory
    memory_manager = MemorySessionManager(
        memory_id=tenant_info['memory_id'],  # "healthcare-basic-memory"
        region_name="us-east-1"
    )
    
    # Create session with user-specific actor_id for isolation
    session = memory_manager.create_memory_session(
        actor_id=tenant_info['actor_id'],  # "basic-clinic-a-dr-smith"
        session_id=context.session_id
    )
    
    # All memory operations now automatically isolated per user
    response = await agent_task(session, payload)
    return response
```

**Why This is Critical**:
- ✅ **User-Level Isolation**: Each user's memories are completely isolated
- ✅ **Clinic-Level Isolation**: Users from different clinics cannot access each other's data
- ✅ **API-Level Enforcement**: AgentCore enforces isolation at the service level
- ✅ **No Cross-Access**: No API exists to access another actor's data
- ✅ **Scalable**: Single Memory resource per tier serves all clinics/users
- ✅ **Cost-Effective**: 2 Memory resources vs 8+ separate resources

**Security Verification Required**:
```python
# Test that User A cannot access User B's memories
user_a_memories = manager.search_long_term_memories(
    query="patient",
    namespace_prefix="clinic/basic-clinic-a-dr-smith/facts",
    top_k=10
)
# Should return only Dr. Smith's data

user_a_trying_user_b = manager.search_long_term_memories(
    query="patient",
    namespace_prefix="clinic/basic-clinic-a-dr-jones/facts",  # Different user
    top_k=10
)
# Should return [] (empty - no cross-user access)
```

**Detailed Documentation**: See "AgentCore Memory Isolation Strategy" section above for complete implementation guide.

### 2. **Document Management System**
**Gap**: No S3 integration for clinical document storage and retrieval
**Requirements**:
- S3 bucket setup with clinic-specific prefixes
- Document indexing and metadata management
- Search functionality across clinic documents
- Document access logging for audit trails
- Pre-upload sample clinical documents per clinic

**Implementation Needed**:
```python
class ClinicalDocumentManager:
    def __init__(self, tier, clinic_id):
        self.s3_prefix = f"{tier}-tier/{clinic_id}/"
        self.bucket = "healthcare-documents"
    
    def search_documents(self, query, doc_types=None):
        # Implement clinic-scoped document search using S3 prefix
        pass
    
    def get_document_content(self, document_id):
        # Retrieve and return document content
        pass
    
    def list_documents(self, clinic_id):
        # List all documents for a specific clinic
        pass
```

**Sample Data Needed**:
- Basic tier: 20-30 documents per clinic (intake forms, notes, basic labs)
- Premium tier: 50-100 documents per clinic (diagnostic reports, imaging studies)

### 2. **Clinical NLP and Processing Tools**
**Gap**: No medical text processing capabilities
**Requirements**:
- Medical terminology recognition
- Clinical entity extraction (medications, conditions, procedures)
- Medical coding (ICD-10, CPT) extraction
- Clinical reasoning and analysis

**Implementation Needed**:
```python
class ClinicalNLPProcessor:
    def extract_medical_entities(self, text):
        # Extract medications, conditions, procedures
        pass
    
    def analyze_clinical_trends(self, documents):
        # Perform trend analysis across documents
        pass
    
    def generate_clinical_summary(self, patient_documents):
        # Create comprehensive patient summary
        pass
```

### 3. **Enhanced Tenant Context Management**
**Gap**: Current system handles basic/premium tiers but needs clinic-level isolation within tiers
**Current Status**: ✅ Tier-level context exists, needs clinic extension
**Requirements**:
- Extend existing `CustomerSupportContext` class to include clinic information
- Add `custom:clinic_id` to Cognito JWT claims
- Document access control per clinic using S3 prefixes
- Clinic-specific tool configurations and routing
- Usage tracking per clinic (extends existing tenant tracking)
- OpenTelemetry baggage for cost attribution

**Implementation Needed**:
```python
# Extend existing context.py in both agent_config/ and agent_config_premium/
class CustomerSupportContext:
    """Enhanced Context Manager with Clinic Support"""
    
    # Add new context variables (extends existing)
    _clinic_id: Optional[str] = None
    _tenant_key: Optional[str] = None  # Combined tier-clinic key
    _s3_prefix: Optional[str] = None   # Document scope prefix
    
    _clinic_id_ctx: ContextVar[Optional[str]] = ContextVar("clinic_id", default=None)
    _tenant_key_ctx: ContextVar[Optional[str]] = ContextVar("tenant_key", default=None)
    _s3_prefix_ctx: ContextVar[Optional[str]] = ContextVar("s3_prefix", default=None)
    
    # New methods (extends existing pattern)
    @classmethod
    def get_clinic_id_ctx(cls) -> Optional[str]:
        if cls._clinic_id:
            return cls._clinic_id
        try:
            return cls._clinic_id_ctx.get()
        except LookupError:
            return None
    
    @classmethod
    def set_clinic_id_ctx(cls, clinic_id: str) -> None:
        cls._clinic_id = clinic_id
        cls._clinic_id_ctx.set(clinic_id)
    
    @classmethod
    def get_tenant_key_ctx(cls) -> Optional[str]:
        """Get combined tier-clinic key (e.g., 'basic-clinic-a')"""
        if cls._tenant_key:
            return cls._tenant_key
        try:
            return cls._tenant_key_ctx.get()
        except LookupError:
            # Fallback: construct from existing context
            tier = cls.get_tenant_id_ctx() or 'basic'
            clinic = cls.get_clinic_id_ctx() or 'demo-clinic'
            return f"{tier}-{clinic}"
    
    @classmethod
    def set_tenant_key_ctx(cls, tenant_key: str) -> None:
        cls._tenant_key = tenant_key
        cls._tenant_key_ctx.set(tenant_key)
    
    @classmethod
    def get_s3_prefix_ctx(cls) -> Optional[str]:
        """Get S3 document prefix for clinic isolation"""
        if cls._s3_prefix:
            return cls._s3_prefix
        try:
            return cls._s3_prefix_ctx.get()
        except LookupError:
            # Fallback: construct from existing context
            tier = cls.get_tenant_id_ctx() or 'basic'
            clinic = cls.get_clinic_id_ctx() or 'demo-clinic'
            return f"{tier}-tier/{clinic}/"
    
    @classmethod
    def set_s3_prefix_ctx(cls, s3_prefix: str) -> None:
        cls._s3_prefix = s3_prefix
        cls._s3_prefix_ctx.set(s3_prefix)
```

### 4. **Frontend Enhancements**
**Gap**: Current Streamlit app needs clinic-aware UI and document-focused chat capabilities
**Requirements**:
- Extend existing Cognito authentication to display clinic information
- Document-aware chat responses with clinical context
- Result visualization for clinical data
- Tier-appropriate UI features based on authenticated tenant
- Clinic-specific branding and document scoping

**Implementation Needed**:
```python
# Enhanced Streamlit interface (extends existing app_modules/)
def render_clinic_header(user_claims):
    """Display clinic information in sidebar (extends existing auth display)"""
    if user_claims:
        st.sidebar.markdown("### 🏥 Clinic Information")
        st.sidebar.write(f"**Clinic:** {user_claims['clinic_id'].replace('-', ' ').title()}")
        st.sidebar.write(f"**Service Tier:** {user_claims['tier'].title()}")
        st.sidebar.write(f"**Role:** {user_claims['role'].title()}")
        st.sidebar.write(f"**User:** {user_claims['username']}")
        
        # Tier-specific feature indicators
        if user_claims['tier'] == 'premium':
            st.sidebar.success("✨ Premium Analytics Enabled")
        else:
            st.sidebar.info("📊 Basic Processing Available")

def render_document_chat_interface(tenant_context):
    """Enhanced chat interface with document context"""
    
    # Document scope indicator
    st.info(f"🔍 Searching documents for: **{tenant_context['clinic_id'].replace('-', ' ').title()}**")
    
    # Tier-specific prompt suggestions
    if tenant_context['tier'] == 'basic':
        st.markdown("**Suggested queries:**")
        st.markdown("- Show me recent patient intake forms")
        st.markdown("- What are common symptoms in recent visits?")
        st.markdown("- List patients with specific conditions")
    else:
        st.markdown("**Advanced analytics available:**")
        st.markdown("- Analyze diagnostic trends across departments")
        st.markdown("- Compare treatment outcomes between protocols")
        st.markdown("- Extract structured data from complex reports")
    
    # Enhanced chat input with document context
    user_input = st.chat_input(
        placeholder=f"Ask about {tenant_context['clinic_id'].replace('-', ' ').title()}'s clinical documents..."
    )
    
    return user_input

def render_clinical_results(response, tenant_context):
    """Structured display of clinical analysis results"""
    
    # Parse response for clinical entities
    if "patients" in response.lower():
        st.markdown("### 👥 Patient Information")
    elif "diagnostic" in response.lower():
        st.markdown("### 🔬 Diagnostic Analysis")
    elif "medication" in response.lower():
        st.markdown("### 💊 Medication Information")
    
    # Display response with clinic context
    st.markdown(response)
    
    # Tier-specific result enhancements
    if tenant_context['tier'] == 'premium':
        st.markdown("---")
        st.markdown("*Advanced analytics powered by Premium tier*")
    
    # Document source attribution
    st.caption(f"📁 Source: {tenant_context['clinic_id'].replace('-', ' ').title()} documents")

# Enhanced main app flow (extends existing app.py structure)
def main():
    auth_manager = AuthManager()
    
    if not auth_manager.is_authenticated():
        # Existing authentication flow
        st.markdown("Please sign in to access your clinic's documents")
        # ... existing login logic ...
    else:
        # Enhanced user claims with clinic info
        user_claims = auth_manager.get_enhanced_user_claims()
        
        # Render clinic-aware header
        render_clinic_header(user_claims)
        
        # Set up tenant context for chat
        tenant_context = {
            'tier': user_claims['tier'],
            'clinic_id': user_claims['clinic_id'],
            'tenant_key': user_claims['tenant_key']
        }
        
        # Enhanced document chat interface
        user_input = render_document_chat_interface(tenant_context)
        
        if user_input:
            # Process with clinic context
            response = process_clinical_query(user_input, tenant_context)
            render_clinical_results(response, tenant_context)
```

### 5. **Web Search Capability (Premium Feature)**
**Gap**: No web search tool integration for premium tier
**Requirements**:
- Integrate web search tool (e.g., Tavily, Brave Search, or custom)
- Configure as premium-only feature
- Add to premium agent tool list
- Enable access to external medical research and guidelines

**Implementation Needed**:
```python
# In agent_config_premium/agent.py
from strands_tools import web_search  # or custom web search tool

class CustomerSupport:
    def __init__(self, ...):
        # Premium tier gets web search
        if tier == 'premium':
            tools = [
                document_search,
                web_search,  # Premium-only feature
                advanced_analytics
            ]
```

**Demo Value**: Shows clear premium differentiation with external data access

### 6. **Sample Data and Document Preparation**
**Gap**: No clinical documents for demonstration
**Requirements**:
- Synthetic clinical documents for each tier
- Realistic patient scenarios
- Variety of document types per clinic specialty
- Anonymized but clinically relevant content

**Data Needed**:
- Basic Tier: 20-30 documents per clinic (intake forms, notes, basic labs)
- Premium Tier: 50-100 documents per clinic (diagnostic reports, imaging, pathology)

### 7. **Configuration and Deployment Updates**
**Gap**: Current deployment needs clinic-level configuration enhancements
**Current Status**: ✅ Tier-level profiles exist, need clinic-specific profiles
**Requirements**:
- Extend `create_inference_profiles.py` for clinic-specific profiles
- Update model IDs to Claude Sonnet 4.5 for premium tier
- SSM parameters for clinic configurations
- AgentCore deployment config for multiple clinics
- Environment variables for clinic routing
- API Gateway usage plans already configured (keep demo limits)
- Monitoring and logging per clinic via observability baggage
- Cost allocation tags in AWS Billing Console

**Configuration Updates Needed**:
```yaml
# .bedrock_agentcore.yaml updates
agents:
  basic_clinical:
    entrypoint: main.py
    environment:
      CLINIC_CONFIGS: "/app/clinics/basic/"
  premium_clinical:
    entrypoint: main_premium.py
    environment:
      CLINIC_CONFIGS: "/app/clinics/premium/"
```

**SSM Parameters for Clinic Configuration**:
```bash
# Store clinic-specific configurations
aws ssm put-parameter \
  --name "/app/healthcare/clinics/clinic-a/tier" \
  --value "basic" \
  --type String

aws ssm put-parameter \
  --name "/app/healthcare/clinics/clinic-a/s3_prefix" \
  --value "basic-tier/clinic-a/" \
  --type String

aws ssm put-parameter \
  --name "/app/healthcare/clinics/hospital-a/tier" \
  --value "premium" \
  --type String

aws ssm put-parameter \
  --name "/app/healthcare/clinics/hospital-a/s3_prefix" \
  --value "premium-tier/hospital-a/" \
  --type String
```

**API Gateway Updates**:
```bash
# Update existing CloudFormation template with production limits
# Edit prerequisite/api_gateway_template.yaml
# Then redeploy:
cd scripts
./deploy_api_gateway.sh
```

## Development Roadmap

### Phase 1: Foundation - Extend Existing Multi-Tenancy (2-3 weeks)
- [ ] 🔴 **CRITICAL: AgentCore Memory Isolation** (Week 1 Priority)
  - [ ] Create 2 Memory resources (basic-tier, premium-tier) with namespace templates
  - [ ] Update JWT parsing to extract `user_id` and construct `actor_id`
  - [ ] Integrate `MemorySessionManager` in `main.py` and `main_premium.py`
  - [ ] Test cross-user and cross-clinic isolation
  - [ ] Store Memory IDs in SSM parameters
  - [ ] Document `actor_id` format and isolation verification
- [ ] **Enhance JWT Processing**: Extend existing `jwt_utils.py` to extract `custom:clinic_id` and `user_id`
- [ ] **Update Context Management**: Add clinic context to existing `CustomerSupportContext` classes
- [ ] **S3 Bucket Setup**: Create clinic-specific document structure
- [ ] **Enhanced Tenant Routing**: Update `main.py` and `main_premium.py` for clinic-level routing
- [ ] **API Gateway Enhancement**: Update Lambda proxy to extract and pass `clinic_id` (keep existing demo rate limits)
- [ ] **Cognito Configuration**: Add `custom:clinic_id` attribute to user pool
- [ ] **Sample Clinical Documents**: Prepare realistic documents for each clinic/tier

### Phase 2: Core Processing - Build on Existing Tools (3-4 weeks)
- [ ] **Document Management Tools**: Create S3-based document search using existing tool patterns
- [ ] **Clinical NLP Processing**: Implement medical text processing tools
- [ ] **Medical Entity Extraction**: Extract medications, conditions, procedures from documents
- [ ] **Enhanced Agent Configuration**: Update existing agent classes for clinical processing
- [ ] **Tool Integration**: Extend existing MCP gateway tools for clinical document access

### Phase 3: Advanced Features - Tier Differentiation (2-3 weeks)
- [ ] **Premium Analytics**: Advanced clinical reasoning for premium tier (extends existing Claude Sonnet 4.5 us
- [ ] **Multi-Document Correlation**: Cross-document analysis and trending
- [ ] **Clinical Decision Support**: Diagnostic pattern recognition and recommendations
- [ ] **Structured Data Extraction**: Convert unstructured notes to structured clinical data
- [ ] **Medical Coding**: Automatic ICD-10, CPT code extraction

### Phase 4: Frontend & Demo - Enhance Existing UI (1-2 weeks)
- [ ] **Streamlit Enhancements**: Extend existing app with clinic-aware UI components
- [ ] **Authentication Display**: Show clinic information in existing auth flow
- [ ] **Document-Focused Chat**: Enhance existing chat interface for clinical queries
- [ ] **Result Visualization**: Clinical data display and formatting
- [ ] **Demo Scenarios**: Create compelling multi-clinic, multi-tier demonstrations
- [ ] **Performance Optimization**: Ensure scalability across multiple clinics

### Implementation Notes
- **Builds on Existing**: Each phase extends current architecture rather than rebuilding
- **Cognito Integration**: Leverages existing OAuth2 flow with enhanced JWT claims
- **AgentCore Runtime**: Uses existing deployment and scaling infrastructure
- **Tool Framework**: Extends existing MCP gateway and tool integration patterns
- **Context Management**: Builds on existing `CustomerSupportContext` architecture

## Success Metrics

### Technical Metrics
- **Memory Isolation**: 100% user-level memory isolation verified (cross-user access returns empty)
- **Tenant Isolation**: 100% document access isolation between clinics
- **Memory Security**: Zero cross-actor memory access (enforced by AgentCore API)
- **Response Time**: Basic tier <5s, Premium tier <2s
- **Accuracy**: >90% accuracy in clinical entity extraction
- **Scalability**: Support 10+ clinics per tier simultaneously with single Memory resource per tier
- **Rate Limiting (Demo)**: 0.5 req/sec (Basic), 2 req/sec (Premium) enforced via API Gateway
- **Throttling Demonstration**: Easy to trigger rate limits during demos to show tier differentiation

### Business Metrics
- **Capability Differentiation**: Clear value difference between tiers (Premium = Basic + Advanced)
- **User Experience**: Intuitive clinic-specific document processing
- **Demo Impact**: Compelling multi-tenancy showcase with visible tier-based throttling
- **Architecture Reusability**: Framework applicable to other domains
- **Upgrade Path**: Clear incentive to upgrade from Basic to Premium (4x rate limits + advanced features)

## Conclusion

This healthcare clinical document processing platform effectively demonstrates sophisticated multi-tenancy capabilities while delivering real clinical value. The two-level tenant model (tiers + clinics) showcases enterprise-grade isolation and differentiation, making it an ideal demonstration of AgentCore's multi-tenant capabilities in a high-value healthcare context.

The scoped approach of pre-uploaded documents with chat-based processing provides a focused, achievable implementation that highlights the core multi-tenancy architecture without getting bogged down in complex upload workflows or compliance requirements.