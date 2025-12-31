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

#### Feature Comparison Matrix 

| Feature Category | Basic Tier | Premium Tier | Multi-Tenancy Capability Demonstrated |
|-----------------|------------|--------------|--------------------------------------|
| **Document Search & Retrieval** | ✅  | ✅  | **Tenant Isolation** - Each clinic sees only their documents |
| **Document Summarization** | ✅  | ✅  | **Model Differentiation** - Nova Micro vs Claude Sonnet 4.5 quality |
| **Data Extraction** | ✅  | ✅  | **Processing Capability** - Tier-based feature access |
| **Web Search Capability** | ❌ | ✅ | **Premium Feature** - Access to external medical research and guidelines | 
| **API Rate Limit (Demo)** | 0.5 req/sec | 2 req/sec | **Resource Allocation** - Tier-based throttling |
| **Burst Limit (Demo)** | 2 requests | 5 requests | **Quota Management** - Fair resource distribution |
| **Daily Quota (Demo)** | 5 requests | 20 requests | **Usage Tracking** - Per-tenant limits |
| **Model** | Nova Micro | Claude Sonnet 4.5 | **Cost Optimization** - Tier-appropriate models |

**Key Multi-Tenancy Demonstrations:**
1. **Isolation**: Clinic A cannot access Clinic B's documents
2. **Differentiation**: Premium gets better models and higher limits
3. **Throttling**: Rate limits enforced per tenant and tier
4. **Cost Tracking**: Usage and costs monitored per clinic for billing/analytics
5. **Premium Features**: Web search capability exclusive to premium tier

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

### 1. **AgentCore Memory Isolation (CRITICAL)** SEE ./memory-architecutre.md for more information
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


### 2. **Enhanced Tenant Context Management** SEE ./technical-architecture.md for more information
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

### 3. **Frontend Enhancements** SEE ./technical-architecture.md for more information
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

### 4. **Web Search Capability (Premium Feature)**
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

### 5. **Sample Data and Document Preparation**
**Gap**: No clinical documents for demonstration
**Requirements**:
- Synthetic clinical documents for each tier
- Realistic patient scenarios
- Variety of document types per clinic specialty
- Anonymized but clinically relevant content

**Data Needed**:
- Basic Tier: 20-30 documents per clinic (intake forms, notes, basic labs)
- Premium Tier: 50-100 documents per clinic (diagnostic reports, imaging, pathology)

### 6. **Configuration and Deployment Updates**
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

This comprehensive roadmap transforms the existing gaming console/financial services multi-tenant system into a healthcare clinical document processing platform. Each phase builds incrementally on existing infrastructure while adding healthcare-specific capabilities.

### Phase 0: Pre-Implementation Planning & Assessment (3-5 days)

**Objective**: Understand current system and plan healthcare transformation

#### 0.1 Current System Analysis
- [x] Review existing gaming console support implementation in `agent_config/`
- [x] Review existing financial services implementation in `agent_config_premium/`
- [x] Document current JWT authentication flow and Cognito configuration 
- [x] Map existing SSM parameters and their usage patterns
- [x] Analyze current inference profile setup and model usage
- [x] Review existing API Gateway configuration and usage plans
- [x] Document current MCP gateway tools and Lambda functions

#### 0.2 Healthcare Requirements Definition
- [ ] Define 8 clinic profiles (4 basic, 4 premium) with specialties
- [ ] Specify document types per clinic tier (intake forms, lab results, etc.)
- [x] Document tier differentiation requirements (Nova Micro vs Claude Sonnet 4.5)
- [x] Plan demo scenarios showcasing multi-tenancy capabilities

#### 0.3 Infrastructure Planning
- [x] Design S3 bucket structure for healthcare documents. This is under ./technical-architecture.md
- [x] Plan Memory resource architecture (2 resources with namespace templates) This is under ./memory-architecture.md
- [ ] Design clinic-specific inference profile strategy
- [x] Plan cost tracking implementation (tags, baggage, observability) This is under ./cost-tracking-capability.md
- [x] Create migration checklist from gaming/finance to healthcare. This documentation is a migration checklist

**Deliverables**: 
- System analysis document
- Healthcare requirements specification
- Infrastructure design diagrams
- Migration plan with rollback strategy

---

### Phase 1: Foundation - Core Multi-Tenancy Infrastructure (2-3 weeks)

**Objective**: Establish healthcare-specific multi-tenancy foundation with complete isolation

#### 1.1 🔴 CRITICAL: AgentCore Memory Isolation (Week 1 Priority - Days 1-3)

**Why Critical**: Memory isolation is the foundation for HIPAA-compliant multi-tenant healthcare. Without proper `actor_id` implementation, clinics and users could access each other's sensitive patient data.

- [ ] **Create Memory Resources** (`scripts/create_memory_resources.py`)
  - [ ] Create `healthcare-basic-memory` with namespace templates:
    - `"clinic/{actorId}/facts/{sessionId}"` - Clinical facts per user
    - `"clinic/{actorId}/preferences"` - User preferences
  - [ ] Create `healthcare-premium-memory` with additional namespaces:
    - `"clinic/{actorId}/insights/{sessionId}"` - Advanced insights
    - `"clinic/{actorId}/analytics"` - Premium analytics data
  - [ ] Set event expiry: 90 days (basic), 180 days (premium)
  - [ ] Store Memory IDs in SSM:
    - `/app/healthcare/memory/basic_id`
    - `/app/healthcare/memory/premium_id`
  - [ ] Verify Memory resources are ACTIVE status

- [ ] **Enable Memory Observability** (`scripts/setup_memory_observability.py`)
  - [ ] Create CloudWatch log groups for both Memory resources
  - [ ] Configure delivery sources (APPLICATION_LOGS, TRACES)
  - [ ] Configure delivery destinations (CloudWatch Logs, X-Ray)
  - [ ] Create deliveries to connect sources to destinations
  - [ ] Verify log groups receiving data:
    - `/aws/vendedlogs/bedrock-agentcore/memory/APPLICATION_LOGS/healthcare-basic-memory`
    - `/aws/vendedlogs/bedrock-agentcore/memory/APPLICATION_LOGS/healthcare-premium-memory`

- [ ] **Update JWT Parsing** (`agent_config/jwt_utils.py`, `agent_config_premium/jwt_utils.py`)
  - [ ] Extract `custom:tenant_id` (tier: basic/premium)
  - [ ] Extract `custom:clinic_id` (clinic identifier)
  - [ ] Extract `cognito:username` (user identifier)
  - [ ] Construct hierarchical `actor_id`: `"{tier}-{clinic_id}-{user_id}"`
  - [ ] Return complete tenant info dict with all isolation keys
  - [ ] Add comprehensive logging for debugging
  - [ ] Implement fallback for missing JWT claims

- [ ] **Integrate MemorySessionManager** (`main.py`, `main_premium.py`)
  - [ ] Initialize `MemorySessionManager` with tier-specific memory ID
  - [ ] Create memory session with user-specific `actor_id`
  - [ ] Configure `retrieval_config` with namespace templates
  - [ ] Implement `process_turn_with_llm` with memory retrieval
  - [ ] Add OpenTelemetry baggage for cost tracking:
    - `tenant_id`, `tier`, `clinic_id`, `actor_id`

- [ ] **Memory Isolation Testing** (`test/test_memory_isolation.py`)
  - [ ] Test same-user access (should succeed)
  - [ ] Test cross-user access within same clinic (should return empty)
  - [ ] Test cross-clinic access (should return empty)
  - [ ] Test cross-tier access (should fail - different Memory resources)
  - [ ] Document test results and isolation guarantees
  - [ ] Create isolation verification runbook

**Deliverables**:
- 2 Memory resources with namespace templates
- Memory observability enabled with CloudWatch integration
- User-level memory isolation via `actor_id`
- Comprehensive isolation test suite

---

#### 1.2 Authentication & Tenant Context (Days 4-6)

- [ ] **Cognito Configuration**
  - [ ] Add `custom:clinic_id` attribute to existing user pool
  - [ ] Add `custom:role` attribute (physician, nurse, admin)
  - [ ] Update user registration flow to capture clinic selection
  - [ ] Create test users for all 8 clinics:
    - Basic: clinic-a, clinic-b, clinic-c, clinic-d
    - Premium: hospital-a, clinic-e, clinic-f, hospital-b
  - [ ] Verify JWT tokens include all custom claims

- [ ] **Enhanced Context Management** (`agent_config/context.py`, `agent_config_premium/context.py`)
  - [ ] Add `_clinic_id` class variable and context var
  - [ ] Add `_tenant_key` (combined tier-clinic identifier)
  - [ ] Add `_s3_prefix` (document scope prefix)
  - [ ] Add `_actor_id` (memory isolation identifier)
  - [ ] Implement getter/setter methods for all new context vars
  - [ ] Add fallback logic for missing context values
  - [ ] Update existing code to use new context methods

- [ ] **Tenant Routing Enhancement** (`main.py`, `main_premium.py`)
  - [ ] Implement `process_tenant_context()` function
  - [ ] Extract tenant info from JWT (primary) or payload (fallback)
  - [ ] Set all context variables (tier, clinic, actor_id, s3_prefix)
  - [ ] Add comprehensive debug logging
  - [ ] Verify context propagation to all downstream operations

**Deliverables**:
- Cognito configured with healthcare-specific claims
- Enhanced context management with clinic-level isolation
- Test users for all 8 clinics

---

#### 1.3 Infrastructure Setup (Days 7-10)

- [ ] **S3 Bucket Structure** (`scripts/setup_s3_buckets.py`)
  - [ ] Create `healthcare-documents-{account-id}` bucket
  - [ ] Create folder structure:
    ```
    basic-tier/
      clinic-a/, clinic-b/, clinic-c/, clinic-d/
    premium-tier/
      hospital-a/, clinic-e/, clinic-f/, hospital-b/
    ```
  - [ ] Configure bucket policies for clinic isolation
  - [ ] Enable versioning and encryption (AES-256)
  - [ ] Configure lifecycle policies (90-day retention for basic, 180-day for premium)
  - [ ] Store bucket name in SSM: `/app/healthcare/s3/bucket_name`

- [ ] **Clinic-Specific Inference Profiles** (`scripts/create_inference_profiles.py`)
  - [ ] Extend existing script for clinic-level profiles
  - [ ] Create profiles for each clinic with tags:
    - `Project=HealthcareDemo`
    - `Tier=basic/premium`
    - `ClinicID=clinic-a/hospital-a/etc`
    - `ClinicName=Family Practice/Multi-specialty Hospital/etc`
  - [ ] Model mapping:
    - Basic: `us.amazon.nova-micro-v1:0`
    - Premium: `us.anthropic.claude-sonnet-4-v2:0` (update from existing)
  - [ ] Store profile ARNs in SSM:
    - `/app/healthcare/inference_profiles/basic/clinic-a`
    - `/app/healthcare/inference_profiles/premium/hospital-a`
    - etc.
  - [ ] Update agent code to use clinic-specific profiles

- [ ] **API Gateway Enhancement** (`prerequisite/lambda/python/api_gateway_lambda.py`)
  - [ ] Update `extract_tenant_info()` to extract `clinic_id` from JWT
  - [ ] Add `clinic_id` to payload forwarded to AgentCore
  - [ ] Add `X-Clinic-ID` response header
  - [ ] Keep existing demo usage plans (no changes needed)
  - [ ] Test routing for all 8 clinics

- [ ] **SSM Parameter Configuration** (`scripts/configure_ssm_parameters.py`)
  - [ ] Store clinic configurations:
    - `/app/healthcare/clinics/{clinic-id}/tier`
    - `/app/healthcare/clinics/{clinic-id}/s3_prefix`
    - `/app/healthcare/clinics/{clinic-id}/specialty`
  - [ ] Store Memory resource IDs
  - [ ] Store inference profile ARNs
  - [ ] Store S3 bucket name
  - [ ] Create parameter retrieval utility functions

**Deliverables**:
- S3 bucket with clinic-specific folder structure
- 8 clinic-specific inference profiles with cost tracking tags
- Enhanced API Gateway with clinic routing
- Complete SSM parameter configuration

---

#### 1.4 Cost Tracking Setup (Days 11-15)

- [ ] **Enable Cost Allocation Tags** (AWS Billing Console)
  - [ ] Activate tags: `ClinicID`, `Tier`, `Project`, `Environment`
  - [ ] Wait 24 hours for tags to appear in Cost Explorer
  - [ ] Verify tags visible in Cost Explorer

- [ ] **OpenTelemetry Baggage Implementation** (`main.py`, `main_premium.py`)
  - [ ] Add baggage context at entrypoint (3 lines):
    ```python
    ctx = baggage.set_baggage("tenant_id", tenant_info['tenant_key'])
    ctx = baggage.set_baggage("tier", tenant_info['tier'])
    ctx = baggage.set_baggage("clinic_id", tenant_info['clinic_id'])
    ctx = baggage.set_baggage("actor_id", tenant_info['actor_id'])
    context.attach(ctx)
    ```
  - [ ] Verify baggage propagates to all operations
  - [ ] Test baggage visibility in CloudWatch Logs

- [ ] **Cost Reporting Setup** (`scripts/generate_cost_report.py`)
  - [ ] Create CloudWatch Logs Insights saved queries:
    - Runtime costs per clinic
    - Memory costs per clinic
    - Combined cost summary
  - [ ] Create Cost Explorer report grouped by ClinicID
  - [ ] Implement Python script to generate monthly cost reports
  - [ ] Test cost attribution for sample workloads

- [ ] **Monitoring Dashboards** (CloudWatch Console)
  - [ ] Create dashboard: "Healthcare Multi-Tenant Overview"
  - [ ] Add widgets:
    - Agent invocations per clinic
    - Memory usage per clinic
    - Model token usage per clinic
    - Error rates per clinic
    - Latency percentiles per tier
  - [ ] Set up alarms for anomalous usage patterns

**Deliverables**:
- Cost allocation tags enabled and visible
- OpenTelemetry baggage for automatic cost attribution
- Cost reporting scripts and saved queries
- CloudWatch monitoring dashboard

---

### Phase 2: Healthcare Domain Implementation (3-4 weeks)

### Phase 2: Healthcare Domain Implementation (3-4 weeks)

**Objective**: Transform gaming/finance agents into healthcare clinical document processing agents

#### 2.1 Sample Clinical Documents (Week 1: Days 1-5)

- [ ] **Document Generation** (`scripts/generate_sample_documents.py`)
  - [ ] Create synthetic clinical documents using LLM
  - [ ] Basic tier document types (20-30 per clinic):
    - Patient intake forms
    - Appointment notes
    - Lab results (basic panels)
    - Prescription records
    - Vital signs logs
  - [ ] Premium tier document types (50-100 per clinic):
    - Diagnostic reports (radiology, pathology)
    - Imaging study reports
    - Surgical notes
    - Specialist consultation notes
    - Complex lab results
  - [ ] Ensure HIPAA-compliant synthetic data (no real PHI)
  - [ ] Add realistic medical terminology and clinical context

- [ ] **Document Upload** (`scripts/upload_documents_to_s3.py`)
  - [ ] Upload documents to clinic-specific S3 prefixes
  - [ ] Add metadata tags (document_type, date, clinic_id)
  - [ ] Verify proper folder structure
  - [ ] Create document inventory manifest per clinic

- [ ] **Knowledge Base Setup** (Optional - if using Bedrock Knowledge Bases)
  - [ ] Create 2 knowledge bases (basic-tier, premium-tier)
  - [ ] Configure S3 data sources with clinic prefixes
  - [ ] Set up embedding models (Titan Embeddings)
  - [ ] Sync documents and verify indexing
  - [ ] Store KB IDs in SSM

**Deliverables**:
- 200-400 synthetic clinical documents across 8 clinics
- Documents uploaded to S3 with proper isolation
- Document inventory and metadata

---

#### 2.2 Clinical Document Tools (Week 2: Days 6-10)

- [ ] **Document Search Tool** (`tools/document_search.py`)
  - [ ] Implement S3-based document search with clinic isolation
  - [ ] Filter by document type, date range, keywords
  - [ ] Respect S3 prefix from tenant context (automatic isolation)
  - [ ] Return document metadata and presigned URLs
  - [ ] Add pagination for large result sets
  - [ ] Integrate with MCP gateway

- [ ] **Document Retrieval Tool** (`tools/document_retrieval.py`)
  - [ ] Fetch document content from S3
  - [ ] Parse common formats (TXT, PDF, JSON)
  - [ ] Extract text content for LLM processing
  - [ ] Implement caching for frequently accessed documents
  - [ ] Add error handling for missing/corrupted documents

- [ ] **Document Summarization Tool** (`tools/document_summarization.py`)
  - [ ] Implement tier-specific summarization:
    - Basic: Nova Micro (fast, cost-effective)
    - Premium: Claude Sonnet 4.5 (high-quality, detailed)
  - [ ] Support single-document and multi-document summarization
  - [ ] Extract key clinical findings
  - [ ] Generate structured summaries (problem list, medications, etc.)

**Deliverables**:
- 3 core document tools integrated with MCP gateway
- Clinic-level isolation enforced in all tools
- Tool testing suite

---

#### 2.4 Agent Refactoring (Week 4: Days 16-20)

- [ ] **Basic Tier Agent** (`agent_config/agent.py`)
  - [ ] Replace gaming console logic with clinical document processing
  - [ ] Update system prompt for healthcare context
  - [ ] Integrate document search, retrieval, summarization tools
  - [ ] Implement basic clinical entity extraction
  - [ ] Configure Nova Micro model via clinic-specific inference profile
  - [ ] Add healthcare-specific conversation flows
  - [ ] Update tool descriptions and examples

- [ ] **Premium Tier Agent** (`agent_config_premium/agent.py`)
  - [ ] Replace financial services logic with advanced clinical analytics
  - [ ] Update system prompt for premium healthcare capabilities
  - [ ] Integrate all basic tools plus premium-only tools:
    - Medical coding
    - Multi-document correlation
    - Advanced analytics
  - [ ] Configure Claude Sonnet 4.5 via clinic-specific inference profile
  - [ ] Implement complex clinical reasoning workflows
  - [ ] Add premium-specific conversation flows

- [ ] **Agent Testing** (`test/test_agents.py`)
  - [ ] Test basic agent with sample clinical queries
  - [ ] Test premium agent with complex scenarios
  - [ ] Verify tool invocations and responses
  - [ ] Test memory persistence across sessions
  - [ ] Validate clinic isolation in agent responses

**Deliverables**:
- Refactored basic and premium agents for healthcare
- Healthcare-specific system prompts and workflows
- Comprehensive agent testing suite

---

### Phase 3: Advanced Features & Tier Differentiation (2-3 weeks)

### Phase 3: Advanced Features & Tier Differentiation (2-3 weeks)

**Objective**: Implement premium-tier exclusive features to demonstrate clear value differentiation

#### 3.1 Premium-Only Features (Week 1: Days 1-7)

- [ ] **Web Search Integration** (`tools/web_search.py`) - Premium Only
  - [ ] Integrate web search tool (Tavily, Brave Search, or custom)
  - [ ] Configure for medical research and clinical guidelines
  - [ ] Search PubMed, medical journals, clinical guidelines
  - [ ] Filter results for credibility and relevance
  - [ ] Add to premium agent tool list only
  - [ ] Test with clinical research queries

- [ ] **Multi-Document Correlation** (`tools/multi_document_analysis.py`) - Premium Only
  - [ ] Analyze multiple documents simultaneously
  - [ ] Identify trends across patient visits
  - [ ] Correlate lab results over time
  - [ ] Track medication changes and outcomes
  - [ ] Generate longitudinal patient summaries
  - [ ] Visualize trends (text-based charts)

- [ ] **Advanced Clinical Analytics** (`tools/clinical_analytics.py`) - Premium Only
  - [ ] Population health analytics across clinic documents
  - [ ] Identify common diagnoses and treatment patterns
  - [ ] Risk stratification based on clinical data
  - [ ] Outcome prediction and trend analysis
  - [ ] Generate clinic-level insights and reports

**Deliverables**:
- 3 premium-exclusive tools demonstrating advanced capabilities
- Clear tier differentiation in feature access
- Premium tool testing suite

---

#### 3.2 Model Differentiation & Performance (Week 2: Days 8-14)

- [ ] **Model Performance Testing** (`test/test_model_performance.py`)
  - [ ] Compare Nova Micro vs Claude Sonnet 4.5 on same queries
  - [ ] Measure response quality, accuracy, detail level
  - [ ] Benchmark latency and token usage
  - [ ] Document cost differences (32x for same usage)
  - [ ] Create comparison report for demo

- [ ] **Tier-Specific Optimizations**
  - [ ] Basic tier: Optimize for speed and cost
    - Shorter prompts
    - Focused tool usage
    - Quick summarization
  - [ ] Premium tier: Optimize for quality and depth
    - Detailed prompts
    - Multi-step reasoning
    - Comprehensive analysis
  - [ ] Document optimization strategies

- [ ] **Rate Limiting Demonstration** (`test/test_rate_limits.py`)
  - [ ] Test basic tier limits (0.5 req/sec, 5/day quota)
  - [ ] Test premium tier limits (2 req/sec, 20/day quota)
  - [ ] Verify throttling behavior
  - [ ] Document user experience differences
  - [ ] Create demo script showing limit enforcement

**Deliverables**:
- Model performance comparison report
- Tier-specific optimization documentation
- Rate limiting demonstration scripts

---

### Phase 4: Frontend & User Experience (2 weeks)

### Phase 4: Frontend & User Experience (2 weeks)

**Objective**: Create compelling healthcare-focused UI demonstrating multi-tenancy capabilities

#### 4.1 Streamlit UI Refactoring (Week 1: Days 1-5)

- [ ] **Authentication Enhancement** (`app_modules/auth.py`)
  - [ ] Extend `get_enhanced_user_claims()` to extract clinic info
  - [ ] Display clinic information in sidebar:
    - Clinic name and specialty
    - Service tier (Basic/Premium)
    - User role (Physician, Nurse, Admin)
    - Username
  - [ ] Add tier-specific badges and indicators
  - [ ] Show available features based on tier

- [ ] **Clinic-Aware Header** (`app_modules/ui_components.py`)
  - [ ] Create `render_clinic_header()` component
  - [ ] Display clinic branding (name, specialty, tier)
  - [ ] Show document scope indicator
  - [ ] Add tier-specific feature highlights
  - [ ] Implement clinic-specific color schemes (optional)

- [ ] **Document-Focused Chat Interface** (`app.py`)
  - [ ] Replace gaming/finance chat with clinical document chat
  - [ ] Add document scope indicator showing clinic context
  - [ ] Implement tier-specific prompt suggestions:
    - Basic: "Show recent patient intake forms", "List lab results"
    - Premium: "Analyze diagnostic trends", "Compare treatment outcomes"
  - [ ] Add document type filters (intake, labs, diagnostics, etc.)
  - [ ] Implement date range filters for document search

- [ ] **Clinical Result Visualization** (`app_modules/result_display.py`)
  - [ ] Create `render_clinical_results()` component
  - [ ] Parse and format clinical entities:
    - Patient information sections
    - Diagnostic findings
    - Medication lists
    - Lab results tables
  - [ ] Add tier-specific result enhancements
  - [ ] Show document source attribution
  - [ ] Implement expandable sections for detailed data

**Deliverables**:
- Healthcare-focused Streamlit UI
- Clinic-aware authentication and branding
- Document-focused chat interface
- Clinical result visualization components

---

#### 4.2 Demo Scenarios & Testing (Week 2: Days 6-10)

- [ ] **Demo Scenario Development** (`demo/scenarios/`)
  - [ ] **Scenario 1: Basic Tier - Family Practice**
    - User: Dr. Smith @ Clinic A
    - Query: "Show me recent patient intake forms"
    - Demonstrates: Document search, basic summarization, clinic isolation
  
  - [ ] **Scenario 2: Basic Tier - Urgent Care**
    - User: Dr. Jones @ Clinic B
    - Query: "What are common symptoms in recent visits?"
    - Demonstrates: Entity extraction, pattern analysis, rate limiting
  
  - [ ] **Scenario 3: Premium Tier - Multi-specialty Hospital**
    - User: Dr. Chen @ Hospital A
    - Query: "Analyze diagnostic trends across departments"
    - Demonstrates: Multi-document analysis, advanced analytics, web search
  
  - [ ] **Scenario 4: Premium Tier - Cardiology Clinic**
    - User: Dr. Patel @ Clinic E
    - Query: "Compare treatment outcomes for hypertension patients"
    - Demonstrates: Longitudinal analysis, outcome tracking, premium features
  
  - [ ] **Scenario 5: Isolation Demonstration**
    - Show Clinic A user cannot access Clinic B documents
    - Show Basic tier user cannot access Premium features
    - Demonstrate rate limit enforcement

- [ ] **Demo Script Creation** (`demo/demo_script.md`)
  - [ ] Write step-by-step demo walkthrough
  - [ ] Include talking points for each scenario
  - [ ] Document expected outputs and key observations
  - [ ] Add troubleshooting tips
  - [ ] Create video recording script

- [ ] **End-to-End Testing** (`test/test_e2e.py`)
  - [ ] Test complete user flows for all 8 clinics
  - [ ] Verify authentication and authorization
  - [ ] Test document search and retrieval
  - [ ] Validate memory persistence across sessions
  - [ ] Test error handling and edge cases
  - [ ] Performance testing under load

**Deliverables**:
- 5 comprehensive demo scenarios
- Demo script with talking points
- End-to-end test suite
- Demo video (optional)

---

### Phase 5: Cost Tracking & Reporting (1 week)

**Objective**: Demonstrate complete cost visibility and attribution per clinic

#### 5.1 Cost Reporting Implementation (Days 1-5)

- [ ] **Cost Data Collection** (`scripts/collect_cost_data.py`)
  - [ ] Query Cost Explorer for model costs by ClinicID tag
  - [ ] Query CloudWatch Logs for runtime costs by baggage.tenant_id
  - [ ] Query CloudWatch Logs for memory costs by tenant_id
  - [ ] Aggregate costs per clinic and tier
  - [ ] Calculate cost per request, per session

- [ ] **Cost Report Generation** (`scripts/generate_cost_report.py`)
  - [ ] Generate monthly cost report per clinic
  - [ ] Break down costs by component:
    - Model invocation costs (Bedrock)
    - Runtime costs (CPU, memory)
    - Memory costs (events, retrievals)
    - API Gateway costs
  - [ ] Calculate total cost per clinic
  - [ ] Generate tier comparison (Basic vs Premium)
  - [ ] Export to CSV and PDF formats

- [ ] **Cost Visualization Dashboard** (CloudWatch or QuickSight)
  - [ ] Create cost dashboard showing:
    - Cost per clinic (bar chart)
    - Cost breakdown by component (pie chart)
    - Cost trends over time (line chart)
    - Tier comparison (side-by-side bars)
  - [ ] Add filters for date range, tier, clinic
  - [ ] Set up automated dashboard refresh

- [ ] **Cost Demo Preparation** (`demo/cost_demo.md`)
  - [ ] Document cost tracking methodology
  - [ ] Show sample cost report for demo clinics
  - [ ] Highlight 32x cost difference (Basic vs Premium)
  - [ ] Demonstrate cost attribution accuracy
  - [ ] Create cost optimization recommendations

**Deliverables**:
- Automated cost reporting scripts
- Monthly cost reports per clinic
- Cost visualization dashboard
- Cost demo documentation

---

### Phase 6: Documentation & Deployment (1 week)

**Objective**: Complete documentation and prepare for production deployment

#### 6.1 Documentation (Days 1-3)

- [ ] **Architecture Documentation** (`docs/architecture.md`)
  - [ ] Update architecture diagrams for healthcare
  - [ ] Document multi-tenancy strategy
  - [ ] Explain memory isolation approach
  - [ ] Document cost tracking implementation
  - [ ] Add security and compliance notes

- [ ] **Deployment Guide** (`docs/deployment.md`)
  - [ ] Step-by-step deployment instructions
  - [ ] Prerequisites and requirements
  - [ ] Configuration checklist
  - [ ] Troubleshooting guide
  - [ ] Rollback procedures

- [ ] **User Guide** (`docs/user_guide.md`)
  - [ ] Clinic administrator guide
  - [ ] End-user guide (physicians, nurses)
  - [ ] Feature comparison (Basic vs Premium)
  - [ ] FAQ and common issues
  - [ ] Support contact information

- [ ] **API Documentation** (`docs/api_reference.md`)
  - [ ] Document all clinical tools and APIs
  - [ ] Provide code examples
  - [ ] Document authentication flow
  - [ ] Add rate limiting information
  - [ ] Include error codes and handling

**Deliverables**:
- Complete architecture documentation
- Deployment and user guides
- API reference documentation

---

#### 6.2 Final Testing & Deployment (Days 4-7)

- [ ] **Integration Testing** (`test/test_integration.py`)
  - [ ] Test all components together
  - [ ] Verify end-to-end workflows
  - [ ] Test failure scenarios and recovery
  - [ ] Load testing with concurrent users
  - [ ] Security testing (isolation, authentication)

- [ ] **Deployment Preparation**
  - [ ] Review all SSM parameters
  - [ ] Verify all AWS resources created
  - [ ] Test deployment script (`deploy.sh`)
  - [ ] Create deployment checklist
  - [ ] Prepare rollback plan

- [ ] **Production Deployment**
  - [ ] Deploy to production environment
  - [ ] Verify all services running
  - [ ] Test with production data
  - [ ] Monitor for errors and issues
  - [ ] Document any deployment issues

- [ ] **Post-Deployment Validation**
  - [ ] Verify authentication working
  - [ ] Test all 8 clinics
  - [ ] Validate cost tracking
  - [ ] Check monitoring dashboards
  - [ ] Confirm memory isolation
  - [ ] Run smoke tests

**Deliverables**:
- Comprehensive integration test suite
- Production deployment
- Post-deployment validation report

---

## Implementation Summary

### Total Timeline: 10-12 weeks

| Phase | Duration | Key Deliverables |
|-------|----------|------------------|
| **Phase 0: Planning** | 3-5 days | System analysis, requirements, infrastructure design |
| **Phase 1: Foundation** | 2-3 weeks | Memory isolation, authentication, infrastructure, cost tracking |
| **Phase 2: Healthcare Domain** | 3-4 weeks | Clinical documents, tools, agent refactoring |
| **Phase 3: Advanced Features** | 2-3 weeks | Premium features, model differentiation, tier optimization |
| **Phase 4: Frontend** | 2 weeks | Streamlit UI, demo scenarios, end-to-end testing |
| **Phase 5: Cost Tracking** | 1 week | Cost reporting, visualization, demo preparation |
| **Phase 6: Documentation** | 1 week | Complete docs, final testing, production deployment |

### Critical Success Factors

1. **Memory Isolation First**: Phase 1.1 is critical - complete memory isolation before proceeding
2. **Incremental Testing**: Test each component thoroughly before moving to next phase
3. **Cost Tracking Early**: Enable observability and cost tracking from Phase 1
4. **Demo-Driven Development**: Keep demo scenarios in mind throughout implementation
5. **Documentation Continuous**: Document as you build, not at the end

### Risk Mitigation

- **Memory Isolation Complexity**: Allocate extra time for Phase 1.1, test thoroughly
- **Model Availability**: Verify Claude Sonnet 4.5 access before Phase 2
- **Cost Tracking Delays**: Enable cost allocation tags early (24-hour activation delay)
- **Scope Creep**: Stick to minimal viable features, defer nice-to-haves
- **Integration Issues**: Test components individually before integration

### Key Architectural Principles

- **Builds on Existing**: Each phase extends current gaming/finance architecture
- **Cognito Integration**: Leverages existing OAuth2 flow with enhanced JWT claims
- **AgentCore Runtime**: Uses existing deployment and scaling infrastructure
- **Tool Framework**: Extends existing MCP gateway and tool integration patterns
- **Context Management**: Builds on existing `CustomerSupportContext` architecture
- **Minimal Changes**: Focus on configuration and content changes over code rewrites

### Demo Value Proposition

This implementation demonstrates:
1. 🔒 **Complete Tenant Isolation**: Clinic A cannot access Clinic B's documents
2. 🎯 **Tier Differentiation**: Premium gets Claude Sonnet 4.5, web search, advanced analytics
3. 🚦 **Resource Allocation**: Rate limits enforced per tier (0.5 vs 2 req/sec)
4. 📊 **Cost Tracking**: Accurate per-clinic cost attribution (32x difference shown)
5. 🌐 **Scalability**: 8 clinics on 2 agent runtimes with complete isolation
6. 💾 **Memory Isolation**: User-level memory separation via `actor_id`
7. 🔐 **Security**: JWT-based authentication with role-based access

The scoped approach of pre-uploaded documents with chat-based processing provides a focused, achievable implementation that highlights core multi-tenancy architecture without complex upload workflows or compliance requirements.