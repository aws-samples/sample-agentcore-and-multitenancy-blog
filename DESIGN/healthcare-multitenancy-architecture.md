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
- [x] Define 8 clinic profiles (4 basic, 4 premium) with specialties
- [x] Specify document types per clinic tier (intake forms, lab results, etc.)
- [x] Document tier differentiation requirements (Nova Micro vs Claude Sonnet 4.5)
- [x] Plan demo scenarios showcasing multi-tenancy capabilities

#### 0.3 Infrastructure Planning
- [x] Design S3 bucket structure for healthcare documents. This is under ./technical-architecture.md
- [x] Plan Memory resource architecture (2 resources with namespace templates) This is under ./memory-architecture.md
- [x] Design clinic-specific inference profile strategy
- [x] Plan cost tracking implementation (tags, baggage, observability) This is under ./cost-tracking-capability.md
- [x] Create migration checklist from gaming/finance to healthcare. This documentation is a migration checklist

**Deliverables**: 
- System analysis document
- Healthcare requirements specification
- Infrastructure design diagrams
- Migration plan with rollback strategy

---

Please see ROADMAP_REORGANIZED.md for following steps

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