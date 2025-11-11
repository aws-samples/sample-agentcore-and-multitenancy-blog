# Healthcare Multi-Tenant Clinical Document Processing Architecture

## Executive Summary

This document outlines the transformation of the existing AgentCore multi-tenancy project into a healthcare clinical document processing platform. The architecture demonstrates sophisticated multi-tenancy patterns with **tier-based service levels** and **multiple tenants per tier**, showcasing complete isolation and differentiated capabilities for clinical document analysis.

### Project Focus: Multi-Tenancy Demonstration (Not Production Healthcare)

This is a **demo project** designed to showcase AgentCore's multi-tenancy capabilities using a healthcare context. The feature set is intentionally streamlined to focus on demonstrating:

1. **Tenant Isolation**: Each clinic accesses only their documents
2. **Tier Differentiation**: Premium tier gets better models and higher limits
3. **Resource Allocation**: API throttling enforced per tier
4. **Scalability**: Multiple clinics per tier with independent configurations
5. **Cost Allocation**: Token budget, allocate agentcore runtime and memory costs to tenant 

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

**Option 1: Single User Pool with Custom Attributes (Recommended)**
```bash
# Add custom attributes to existing Cognito User Pool
aws cognito-idp add-custom-attributes \
  --user-pool-id us-east-1_JlX0bKAgU \
  --custom-attributes Name=clinic_id,AttributeDataType=String,Required=true

# Users register with clinic selection
# JWT automatically includes custom:clinic_id claim
```

**Option 2: Multiple App Clients per Clinic**
```python
# Different app clients for different clinics
clinic_app_clients = {
    "clinic-a": "1amjs2urmd54i5hlerind8b7sg",  # Basic tier
    "clinic-b": "2bmkt3vsne65j6imfsojoe8c8t",  # Basic tier  
    "hospital-a": "3cnlu4wtof76k7jngtpkpf9d9u", # Premium tier
}

# Each app client configured with different custom attribute defaults
```

**Option 3: Clinic-Specific Login URLs**
```python
# Different login URLs that set clinic context
login_urls = {
    "clinic-a": "https://your-app.com/login?clinic=clinic-a",
    "hospital-a": "https://your-app.com/login?clinic=hospital-a"
}

# Login flow sets clinic_id in JWT claims during authentication
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
[Advanced analysis using Claude Sonnet 4.5 - multi-document correlation]"

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
    
    # Model mapping
    models = {
        'basic': 'us.amazon.nova-micro-v1:0',
        'premium': 'us.anthropic.claude-sonnet-4-5-20250929-v1:0'
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
    modelId='us.anthropic.claude-sonnet-4-5-20250929-v1:0',
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

```python
# In main.py and main_premium.py - Add tenant context to all operations
from opentelemetry import baggage, context
import os

@app.entrypoint
async def invoke(payload, context_obj):
    # Extract tenant info (already implemented)
    tenant_info = process_tenant_context(payload, context_obj.headers or {})
    
    # Set OpenTelemetry baggage for cost attribution
    ctx = baggage.set_baggage("tenant_id", tenant_info['tenant_key'])
    ctx = baggage.set_baggage("tier", tenant_info['tier'])
    ctx = baggage.set_baggage("clinic_id", tenant_info['clinic_id'])
    context.attach(ctx)
    
    # All subsequent operations will include this tenant context
    # Runtime, Memory, and Tool costs will be tagged with tenant info
    response = await agent_task(...)
    return response
```

**Viewing Costs in CloudWatch**:

1. **GenAI Observability Dashboard**:
   - Navigate to CloudWatch → GenAI Observability → Bedrock AgentCore
   - Filter by `tenant_id` baggage attribute
   - View Runtime metrics per clinic:
     - CPU usage (vCPU-seconds)
     - Memory usage (GB-seconds)
     - Session duration
     - Token consumption

2. **CloudWatch Logs Insights**:
```sql
# Query Runtime costs per tenant
fields @timestamp, tenant_id, tier, clinic_id, 
       runtime.cpu_seconds, runtime.memory_gb_seconds
| filter tenant_id like /clinic-/
| stats sum(runtime.cpu_seconds) as total_cpu,
        sum(runtime.memory_gb_seconds) as total_memory
  by tenant_id, tier
| sort total_cpu desc
```

3. **Memory Service Costs**:
```sql
# Query Memory usage per tenant
fields @timestamp, tenant_id, memory.events, memory.retrievals
| filter tenant_id like /clinic-/
| stats sum(memory.events) as total_events,
        sum(memory.retrievals) as total_retrievals
  by tenant_id
```

**Cost Calculation Example**:

```python
# Clinic A (Basic Tier) - Monthly Usage
runtime_cpu_seconds = 3600  # 1 hour of CPU time
runtime_memory_gb_seconds = 1800  # 0.5 GB for 1 hour
memory_events = 10000
memory_retrievals = 5000

# Calculate costs
runtime_cpu_cost = 3600 * 0.000011 = $0.0396
runtime_memory_cost = 1800 * 0.0000012 = $0.00216
memory_events_cost = 10000 * 0.000001 = $0.01
memory_retrievals_cost = 5000 * 0.000004 = $0.02

total_agentcore_cost = $0.07176

# Add model costs from inference profile
model_cost = $5.00  # From tagged inference profile

# Total cost for Clinic A
total_cost = $5.07176
```

**Benefits**:
- ✅ Automatic cost attribution per tenant via baggage
- ✅ No code changes needed (observability already enabled)
- ✅ Real-time visibility in CloudWatch dashboards
- ✅ Granular tracking: Runtime, Memory, Tools, Models
- ✅ Query-able logs for custom cost reports

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
- [ ] Extend `create_inference_profiles.py` to create clinic-specific profiles
- [ ] Add OpenTelemetry baggage in `main.py` and `main_premium.py`
- [ ] Update agent classes to use clinic-specific profiles from SSM
- [ ] Test cost attribution in CloudWatch Logs

**Phase 2: Enable Cost Reporting (1 week)**
- [ ] Enable cost allocation tags in AWS Billing Console (ClinicID, Tier)
- [ ] Create CloudWatch Logs Insights queries for per-tenant costs
- [ ] Set up simple Cost Explorer report grouped by ClinicID
- [ ] Export sample cost report to CSV

**Phase 3: Demo Dashboard (Optional, 1 week)**
- [ ] Create QuickSight dataset from CloudWatch Logs
- [ ] Build simple per-tenant cost dashboard
- [ ] Add cost breakdown visualizations
- [ ] Set up automated monthly reports

**Quick Win: Immediate Cost Visibility**

Without any code changes, you can see costs today:

1. **CloudWatch GenAI Observability**:
   - Already enabled in your `.bedrock_agentcore.yaml`
   - View Runtime/Memory metrics per agent
   - Filter by session to see per-request costs

2. **AWS Cost Explorer**:
   - View Bedrock costs by inference profile tags
   - Current tags: Project=CustomerSupport, Tier=Basic/Premium
   - Add ClinicID tag for per-clinic breakdown

3. **CloudWatch Logs**:
   - Query invocation logs for token usage
   - Calculate model costs: (input_tokens * $0.0008) + (output_tokens * $0.0016)
   - Group by tenant_id from request metadata

### Per-Tenant Cost Reporting

**Primary Goal**: Track and report costs per clinic (tenant) for billing/chargeback

**Cost Components Per Tenant**:
1. **Model Costs**: Bedrock invocations (via tagged inference profiles)
2. **Runtime Costs**: CPU + Memory consumption (via observability baggage)
3. **Memory Costs**: Events + Retrievals (via observability baggage)
4. **Tool Costs**: Gateway, Browser, Code Interpreter (via observability baggage)
5. **API Gateway**: Request costs (via usage plans)

**Simple Per-Tenant Reporting Dashboard**:

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

**QuickSight Dashboard (Simplified)**:

Single dashboard with per-tenant views:

1. **Cost Summary Table**:
```
Clinic ID    | Tier    | Model $ | Runtime $ | Memory $ | Tools $ | Total $
-------------|---------|---------|-----------|----------|---------|--------
clinic-a     | basic   | $5.20   | $0.08     | $0.03    | $0.00   | $5.31
clinic-b     | basic   | $3.80   | $0.05     | $0.02    | $0.00   | $3.87
hospital-a   | premium | $45.60  | $1.20     | $0.45    | $2.10   | $49.35
clinic-e     | premium | $32.40  | $0.90     | $0.30    | $1.50   | $35.10
```

2. **Cost Breakdown Chart** (Per Tenant):
   - Bar chart showing cost components per clinic
   - Filter by date range
   - Drill-down to daily/hourly costs

3. **Tier Comparison**:
   - Average cost per clinic by tier
   - Basic tier average: $4.50/month
   - Premium tier average: $42.00/month

**AWS Cost Explorer View**:

1. Enable cost allocation tags:
   - `ClinicID`
   - `Tier`
   - `Project`

2. Create Cost Explorer report:
   - Group by: Tag → ClinicID
   - Filter: Service → Bedrock, AgentCore Runtime, AgentCore Memory
   - Time range: Last 30 days

3. Export to CSV for billing:
```csv
ClinicID,Tier,BedrockCost,RuntimeCost,MemoryCost,TotalCost
clinic-a,basic,$5.20,$0.08,$0.03,$5.31
clinic-b,basic,$3.80,$0.05,$0.02,$3.87
hospital-a,premium,$45.60,$1.20,$0.45,$49.35
```

### Cost Optimization Strategies

1. **Tier-Appropriate Models**: Basic uses Nova Micro, Premium uses Claude
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
- Multi-tenant agent architecture with tier separation
- JWT-based authentication and tenant routing
- AgentCore runtime with session management
- Streamlit chat interface foundation
- SSM parameter store configuration
- Memory management and conversation persistence

#### ❌ **Implementation Gaps**

### 1. **Document Management System**
**Gap**: No S3 integration for clinical document storage and retrieval
**Requirements**:
- S3 bucket setup with clinic-specific prefixes
- Document indexing and metadata management
- Search functionality across clinic documents
- Document access logging for audit trails

**Implementation Needed**:
```python
class ClinicalDocumentManager:
    def __init__(self, tier, clinic_id):
        self.s3_prefix = f"{tier}-tier/{clinic_id}/"
        self.bucket = "healthcare-documents"
    
    def search_documents(self, query, doc_types=None):
        # Implement clinic-scoped document search
        pass
    
    def get_document_content(self, document_id):
        # Retrieve and return document content
        pass
```

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
**Requirements**:
- Extend existing `CustomerSupportContext` class to include clinic information
- Document access control per clinic using S3 prefixes
- Clinic-specific tool configurations and routing
- Usage tracking per clinic (extends existing tenant tracking)

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

### 5. **Sample Data and Document Preparation**
**Gap**: No clinical documents for demonstration
**Requirements**:
- Synthetic clinical documents for each tier
- Realistic patient scenarios
- Variety of document types per clinic specialty
- Anonymized but clinically relevant content

**Data Needed**:
- Basic Tier: 50-100 documents per clinic (intake forms, notes, basic labs)
- Premium Tier: 100-200 documents per clinic (diagnostic reports, imaging, pathology)

### 6. **Configuration and Deployment Updates**
**Gap**: Current deployment needs clinic-level configuration enhancements
**Requirements**:
- SSM parameters for clinic configurations
- AgentCore deployment config for multiple clinics
- Environment variables for clinic routing
- Update existing API Gateway usage plans for production limits
- Monitoring and logging per clinic

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
- [ ] **Enhance JWT Processing**: Extend existing `jwt_utils.py` to extract `custom:clinic_id`
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
- [ ] **Premium Analytics**: Advanced clinical reasoning for premium tier (extends existing Claude usage)
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
- **Tenant Isolation**: 100% document access isolation between clinics
- **Response Time**: Basic tier <5s, Premium tier <2s
- **Accuracy**: >90% accuracy in clinical entity extraction
- **Scalability**: Support 10+ clinics per tier simultaneously
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