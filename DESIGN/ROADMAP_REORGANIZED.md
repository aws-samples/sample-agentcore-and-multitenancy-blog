# Healthcare Multi-Tenancy Development Roadmap (Reorganized)

**Based on deploy.sh deployment flow**

This roadmap follows a proper development workflow: **Code changes FIRST, then deployment**. The code refactoring happens before running `deploy.sh` to ensure healthcare-specific logic is in place during infrastructure setup.

## Phase 1: Code Refactoring & Preparation (Week 1: 5-7 days)

**Objective**: Refactor existing gaming/finance code to healthcare BEFORE deployment

**Critical**: All code changes must be completed before running `deploy.sh`

### 1.1 Environment Setup & Configuration Updates (Day 1)

- [ ] **Python Environment**
  - [ ] Create virtual environment: `python -m venv .venv`
  - [ ] Activate: `source .venv/bin/activate`
  - [ ] Install dependencies: `pip install -r dev-requirements.txt`
  - [ ] Verify AgentCore CLI installed: `agentcore --version`

- [ ] **Update All Configuration Files** (BEFORE deployment)
  - [ ] Update `deploy.sh`:
    - Change `BUCKET_NAME=customersupport` → `BUCKET_NAME=healthcare`
    - Change agent names: `healthcare-basic`, `healthcare-premium`
    - Update all references to `customersupport` → `healthcare`
    - **Add new steps per DEPLOY_SH_UPDATES.md**:
      - Add memory observability setup (after memory creation)
      - Add Cognito user creation (after agent configuration)
      - Add S3 document bucket setup (optional)
      - Update final success message with healthcare context
  - [ ] Update `scripts/prereq.sh`:
    - Change default bucket name to `healthcare`
    - Change stack names: `HealthcareStackInfra`, `HealthcareStackCognito`
  - [ ] Update CloudFormation templates in `prerequisite/`:
    - **`cognito.yaml`**:
      - Add custom attributes to UserPool:
        ```yaml
        Schema:
          - Name: tenant_id
            AttributeDataType: String
            Mutable: true
          - Name: clinic_id
            AttributeDataType: String
            Mutable: true
          - Name: role
            AttributeDataType: String
            Mutable: true
        ```
      - Update resource names and descriptions for healthcare
      - Update SSM parameter paths: `/app/healthcare/*`
    - **`infrastructure.yaml`**:
      - Update SSM parameter paths: `/app/healthcare/*`
      - Integrate API Gateway usage plans (from `api_gateway_template.yaml`):
        - Basic tier: 0.5 req/sec, burst 2, quota 5/day
        - Premium tier: 2 req/sec, burst 5, quota 20/day
      - Update resource names for healthcare
    - Change KB names: `healthcare-basic-kb`, `healthcare-premium-kb`
    - Update S3 data source paths for healthcare documents
    - Update SSM parameter paths: `/app/healthcare/knowledge_base/*`
  - [ ] Update `prerequisite/lambda/python/api_gateway_lambda.py`:
    - Update `extract_tenant_info()` to extract `clinic_id` from JWT:
      ```python
      clinic_id = claims.get('custom:clinic_id', 'demo-clinic')
      ```
    - Add `clinic_id` to payload forwarded to AgentCore
    - Add `X-Clinic-ID` response header
  - [ ] Update `scripts/create_inference_profiles.py`:
    - Profile names: `healthcare-basic-profile`, `healthcare-premium-profile` (2 tier-level profiles)
    - Model IDs:
      - Basic: `us.amazon.nova-micro-v1:0`
      - Premium: `us.anthropic.claude-sonnet-4-v2:0`
    - Tags: `Project=HealthcareDemo`, `Tier=Basic/Premium`, `Environment=demo`
    - SSM paths: `/app/healthcare/inference_profiles/basic_arn`, `premium_arn`
  - [ ] Update `scripts/configure_deployment.py`:
    - Change SSM parameter paths to `/app/healthcare/*`
    - Update regex patterns for healthcare naming
  - [ ] Update `scripts/agentcore_gateway.py`:
    - Support creating 2 gateways: `healthcare-basic-gw`, `healthcare-premium-gw`
    - Each gateway will have tier-specific tools
  - [ ] Update `scripts/cognito_credentials_provider.py`:
    - Support 2 credential providers: `healthcare-basic-gateways`, `healthcare-premium-gateways`
  - [ ] Update `scripts/agentcore_memory.py`:
    - Add namespace template support
    - Default names: `healthcare-basic-memory`, `healthcare-premium-memory`

**Deliverables**: 
- Working Python environment
- All configuration files updated for healthcare (NOT deployed yet)
- Cognito custom attributes defined in CloudFormation
- API Gateway Lambda proxy updated to extract clinic_id
- Knowledge base script updated for healthcare
- 2 tier-level inference profiles configured (not 8 clinic-level)

---

### 1.2 JWT Parsing & Tenant Context (Day 2)

**Critical**: Update JWT parsing BEFORE deployment so agents understand clinic context

- [ ] **Update JWT Utilities** (`agent_config/jwt_utils.py`, `agent_config_premium/jwt_utils.py`)
  - [ ] Extract `custom:tenant_id` (tier: basic/premium)
  - [ ] Extract `custom:clinic_id` (clinic identifier)
  - [ ] Extract `cognito:username` (user identifier)
  - [ ] Construct hierarchical `actor_id`: `"{tier}-{clinic_id}-{user_id}"`
  - [ ] Return complete tenant info dict:
    ```python
    {
        'tier': 'basic',
        'clinic_id': 'clinic-a',
        'user_id': 'dr-smith',
        'actor_id': 'basic-clinic-a-dr-smith',
        'tenant_key': 'basic-clinic-a',
        'memory_id': 'healthcare-basic-memory',
        's3_prefix': 'basic-tier/clinic-a/'
    }
    ```
  - [ ] Add comprehensive logging
  - [ ] Implement fallback for missing claims

- [ ] **Enhanced Context Management** (`agent_config/context.py`, `agent_config_premium/context.py`)
  - [ ] Add `_clinic_id` class variable and context var
  - [ ] Add `_tenant_key` (combined tier-clinic identifier)
  - [ ] Add `_s3_prefix` (document scope prefix)
  - [ ] Add `_actor_id` (memory isolation identifier)
  - [ ] Implement getter/setter methods for all new context vars
  - [ ] Add fallback logic for missing context values

**Deliverables**:
- Enhanced JWT parsing with clinic extraction
- Extended context management for clinic isolation
- Code ready for deployment (NOT deployed yet)

---

### 1.3 Agent Entrypoint Updates (Day 3)

**Critical**: Add OpenTelemetry baggage and memory integration BEFORE deployment

- [ ] **Update main.py (Basic Tier)**
  - [ ] Import OpenTelemetry baggage: `from opentelemetry import baggage, context`
  - [ ] Update `@app.entrypoint` function:
    - [ ] Extract tenant info from JWT using updated `jwt_utils`
    - [ ] Set OpenTelemetry baggage (3 lines):
      ```python
      ctx = baggage.set_baggage("tenant_id", tenant_info['tenant_key'])
      ctx = baggage.set_baggage("tier", tenant_info['tier'])
      ctx = baggage.set_baggage("clinic_id", tenant_info['clinic_id'])
      ctx = baggage.set_baggage("actor_id", tenant_info['actor_id'])
      context.attach(ctx)
      ```
    - [ ] Initialize MemorySessionManager with tier-specific memory
    - [ ] Create memory session with user-specific actor_id
    - [ ] Pass tenant context to agent

- [ ] **Update main_premium.py (Premium Tier)**
  - [ ] Same changes as main.py
  - [ ] Ensure premium memory ID used
  - [ ] Verify premium-specific features enabled

**Deliverables**:
- Updated agent entrypoints with baggage and memory integration
- Code ready for deployment (NOT deployed yet)

---

### 1.4 Agent Class Refactoring (Days 4-5)

**Critical**: Replace gaming/finance logic with healthcare BEFORE deployment

- [ ] **Update agent_config/agent.py (Basic Tier)**
  - [ ] Replace gaming console system prompt with healthcare prompt:
    ```python
    system_prompt = """
    You are a helpful clinical document assistant for a healthcare clinic.
    You help physicians and nurses search, retrieve, and summarize clinical documents.
    
    AVAILABLE TOOLS:
    - document_search: Search clinic documents by type, date, keywords
    - document_retrieval: Retrieve full document content
    - document_summarization: Summarize clinical documents
    - retrieve: Search knowledge base for medical information
    - current_time: Get current date and time
    
    IMPORTANT:
    - You can only access documents for your assigned clinic
    - Maintain patient confidentiality at all times
    - Provide concise, clinically relevant summaries
    - Always cite document sources
    """
    ```
  - [ ] Update tool list for healthcare (placeholder tools for now)
  - [ ] Remove gaming console-specific tools
  - [ ] Keep inference profile mapping logic (already correct)
  - [ ] Update MCP gateway headers to include clinic_id

- [ ] **Update agent_config_premium/agent.py (Premium Tier)**
  - [ ] Update system prompt for premium healthcare capabilities
  - [ ] Add premium-only tools (placeholder for now)
  - [ ] Keep Claude Sonnet 4.5 model configuration
  - [ ] Update tool descriptions for clinical context

**Deliverables**:
- Refactored agent classes with healthcare prompts
- Updated tool configurations
- Code ready for deployment (NOT deployed yet)

---

### 1.5 Create Memory Observability Script (Day 6)

**Critical**: Create script BEFORE deployment so it's ready to run after memory resources are created

- [ ] **Create scripts/setup_memory_observability.py**
  - [ ] Implement function to enable observability for Memory resources
  - [ ] Create CloudWatch log groups
  - [ ] Configure delivery sources (APPLICATION_LOGS, TRACES)
  - [ ] Configure delivery destinations (CloudWatch Logs, X-Ray)
  - [ ] Create deliveries to connect sources to destinations
  - [ ] Accept memory IDs as parameters
  - [ ] Add error handling and verification

- [ ] **Create scripts/create_test_users.py**
  - [ ] Script to create Cognito users with custom attributes
  - [ ] Support for 8 clinic users (4 basic, 4 premium)
  - [ ] Set custom:clinic_id and custom:tenant_id attributes
  - [ ] Generate credentials document

**Deliverables**:
- Memory observability script ready
- User creation script ready
- Scripts NOT executed yet (will run after deployment)

---

### 1.6 Update Knowledge Base Script (Day 7)

**Critical**: Update KB script to use healthcare naming BEFORE deployment

- [ ] **Update prerequisite/knowledge_base.py**
  - [ ] Change KB names: `healthcare-basic-kb`, `healthcare-premium-kb`
  - [ ] Update S3 data source paths for healthcare documents
  - [ ] Update SSM parameter paths: `/app/healthcare/knowledge_base/*`
  - [ ] Update descriptions for healthcare context

**Deliverables**:
- Knowledge base script updated for healthcare
- Code ready for deployment

---

## Phase 2: Infrastructure Deployment (Week 2: 3-5 days)

**Objective**: Deploy healthcare infrastructure using refactored code

**Now we run deploy.sh with healthcare-ready code**

### 2.1 AWS Infrastructure Deployment (Day 1)

**Follows**: `deploy.sh` lines 34-36 → `scripts/prereq.sh`

- [ ] **Run Infrastructure Setup**
  - [ ] Execute: `chmod +x scripts/prereq.sh && ./scripts/prereq.sh`
  - [ ] Creates S3 bucket: `healthcare-{account-id}`
  - [ ] Deploys CloudFormation stacks:
    - `HealthcareStackInfra` (IAM roles, ECR repos)
    - `HealthcareStackCognito` (User pool, app client)
  - [ ] Creates Knowledge Bases: `healthcare-basic-kb`, `healthcare-premium-kb`
  - [ ] Stores all resource IDs in SSM: `/app/healthcare/*`

- [ ] **Verify Infrastructure**
  - [ ] Check CloudFormation stacks: `COMPLETE` status
  - [ ] Check S3 bucket created
  - [ ] Check Knowledge Bases: `ACTIVE` status
  - [ ] List SSM parameters: `./scripts/list_ssm_parameters.sh`

**Deliverables**:
- S3 bucket with Lambda code
- 2 CloudFormation stacks deployed
- 2 Knowledge Bases created
- SSM parameters populated

---

### 2.2 Inference Profiles & Configuration (Day 2 - Morning)

**Follows**: `deploy.sh` lines 38-43

- [ ] **Create Inference Profiles**
  - [ ] Run: `python scripts/create_inference_profiles.py`
  - [ ] Creates:
    - `healthcare-basic-profile` with Nova Micro
    - `healthcare-premium-profile` with Claude Sonnet 4.5
  - [ ] Stores ARNs in SSM: `/app/healthcare/inference_profiles/*`

- [ ] **Update Deployment Configuration**
  - [ ] Run: `python scripts/configure_deployment.py`
  - [ ] Updates agent files with profile ARNs
  - [ ] Generates `.bedrock_agentcore.yaml`

- [ ] **Verify Configuration**
  - [ ] Run: `./scripts/list_ssm_parameters.sh`
  - [ ] Verify all healthcare parameters present
  - [ ] Check agent files have correct ARNs

**Deliverables**:
- 2 inference profiles created
- Agent configuration files updated
- SSM parameters verified

---

### 2.3 AgentCore Gateway & Credentials (Day 2 - Afternoon)

**Follows**: `deploy.sh` lines 47-52 (adapted for 2 gateways)

- [ ] **Create AgentCore Gateways** (2 gateways for tier-specific tools)
  - [ ] Create basic tier gateway:
    ```bash
    python scripts/agentcore_gateway.py create --name healthcare-basic-gw
    ```
  - [ ] Create premium tier gateway:
    ```bash
    python scripts/agentcore_gateway.py create --name healthcare-premium-gw
    ```
  - [ ] Verify both gateways created and active
  - [ ] Store gateway URLs in SSM:
    - `/app/healthcare/agentcore/basic_gateway_url`
    - `/app/healthcare/agentcore/premium_gateway_url`

- [ ] **Setup Cognito Credential Providers** (2 providers, one per gateway)
  - [ ] Create basic tier credential provider:
    ```bash
    python scripts/cognito_credentials_provider.py create --name healthcare-basic-gateways
    ```
  - [ ] Create premium tier credential provider:
    ```bash
    python scripts/cognito_credentials_provider.py create --name healthcare-premium-gateways
    ```
  - [ ] Links Cognito to respective AgentCore gateways
  - [ ] Verify both credential providers active

- [ ] **Register Tools with Gateways**
  - [ ] Register basic tools with basic gateway:
    - Document search (Lambda target)
    - Document retrieval (Lambda target)
    - Document summarization (Lambda target)
  - [ ] Register premium tools with premium gateway:
    - All basic tools (Lambda targets)
    - Web search (Lambda target) - Premium only
  - [ ] Use `scripts/agentcore_gateway.py` target registration functionality
  - [ ] Verify tool registration for both gateways

- [ ] **Test Gateways** (with placeholder prompts)
  - [ ] Test basic gateway: `python test/test_gateway.py --gateway basic --prompt "Test healthcare gateway"`
  - [ ] Test premium gateway: `python test/test_gateway.py --gateway premium --prompt "Test healthcare gateway with web search"`
  - [ ] Verify both gateways respond
  - [ ] Verify tenant routing works

**Deliverables**:
- 2 AgentCore Gateways deployed (basic and premium)
- 2 Cognito credential providers configured
- Tools registered with respective gateways
- Premium-only tool access enforced via separate gateway
- Gateways tested

---

### 2.4 Memory Resources & Observability (Day 3)

**Follows**: `deploy.sh` lines 54-61 (adapted)

- [ ] **Create Memory Resources**
  - [ ] Run:
    ```bash
    python scripts/agentcore_memory.py create \
      --name healthcare-basic-memory \
      --namespaces "clinic/{actorId}/facts/{sessionId}" "clinic/{actorId}/preferences" \
      --expiry-days 90
    ```
  - [ ] Run:
    ```bash
    python scripts/agentcore_memory.py create \
      --name healthcare-premium-memory \
      --namespaces "clinic/{actorId}/insights/{sessionId}" "clinic/{actorId}/preferences" "clinic/{actorId}/analytics" \
      --expiry-days 180
    ```
  - [ ] Verify memory resources: `ACTIVE` status
  - [ ] Memory IDs stored in SSM

- [ ] **Enable Memory Observability** (NOW we run the script we created)
  - [ ] Run:
    ```bash
    python scripts/setup_memory_observability.py \
      --memory-id healthcare-basic-memory \
      --memory-id healthcare-premium-memory
    ```
  - [ ] Verify CloudWatch log groups created
  - [ ] Verify X-Ray traces enabled

- [ ] **Test Memory Functionality**
  - [ ] Run: `python test/test_memory.py load-conversation`
  - [ ] Run: `python test/test_memory.py load-prompt "Patient prefers morning appointments"`
  - [ ] Verify memory isolation per actor_id

**Deliverables**:
- 2 Memory resources with namespace templates
- Memory observability enabled
- Memory functionality tested

---

### 2.5 Agent Configuration & Cognito Users (Day 4)

**Follows**: `deploy.sh` lines 63-77 + user setup

- [ ] **Configure Agents**
  - [ ] Get runtime role: `RUNTIME_ROLE=$(./scripts/list_ssm_parameters.sh | grep runtime_iam_role | cut -d'=' -f2)`
  - [ ] Configure basic agent:
    ```bash
    agentcore configure --entrypoint main.py \
      -er "$RUNTIME_ROLE" \
      --name healthcare-basic
    ```
  - [ ] Configure premium agent:
    ```bash
    agentcore configure --entrypoint main_premium.py \
      -er "$RUNTIME_ROLE" \
      --name healthcare-premium
    ```
  - [ ] Clean up: `rm -f .agentcore.yaml`

- [ ] **Add Custom Attributes to Cognito**
  - [ ] Add `custom:clinic_id` attribute to user pool
  - [ ] Add `custom:role` attribute
  - [ ] Update user pool schema

- [ ] **Create Test Users** (NOW we run the script we created)
  - [ ] Run: `python scripts/create_test_users.py`
  - [ ] Creates 8 users (4 basic, 4 premium)
  - [ ] Sets custom:clinic_id and custom:tenant_id
  - [ ] Generates credentials document

- [ ] **Verify JWT Tokens**
  - [ ] Test login with one user
  - [ ] Decode JWT token
  - [ ] Verify custom attributes present

**Deliverables**:
- 2 AgentCore agents configured
- Cognito user pool with custom attributes
- 8 test users created
- JWT tokens verified

---

### 2.6 Test Baggage Propagation (Day 5)

**Critical**: Verify healthcare context is working

- [ ] **Launch Agents**
  - [ ] Run: `agentcore launch`
  - [ ] Verify both agents running
  - [ ] Check agent health endpoints

- [ ] **Send Test Requests**
  - [ ] Authenticate as `dr-smith@clinic-a.demo`
  - [ ] Send test query to basic agent
  - [ ] Authenticate as `dr-chen@hospital-a.demo`
  - [ ] Send test query to premium agent

- [ ] **Verify Baggage in CloudWatch Logs**
  - [ ] Check logs for `baggage.tenant_id`
  - [ ] Check logs for `baggage.clinic_id`
  - [ ] Check logs for `baggage.actor_id`
  - [ ] Verify values match expected clinic context

- [ ] **Verify Memory Isolation**
  - [ ] Send queries from different users
  - [ ] Verify memory is isolated per actor_id
  - [ ] Check CloudWatch Logs for memory operations

**Deliverables**:
- Agents running with healthcare context
- Baggage propagation verified
- Memory isolation verified

---

## Phase 3: Clinical Document Tools & S3 Setup (Week 3: 5-7 days)

**Objective**: Implement healthcare-specific tools and document storage

### 3.1 S3 Document Structure Setup (Days 1-2)

### 3.1 S3 Document Structure Setup (Days 1-2)

- [ ] **Create S3 Bucket for Documents** (`scripts/setup_s3_buckets.py`)
  - [ ] Create bucket: `healthcare-documents-{account-id}`
  - [ ] Create folder structure:
    ```
    basic-tier/
      clinic-a/, clinic-b/, clinic-c/, clinic-d/
    premium-tier/
      hospital-a/, clinic-e/, clinic-f/, hospital-b/
    ```
  - [ ] Configure bucket policies for clinic isolation
  - [ ] Enable versioning and encryption (AES-256)
  - [ ] Store bucket name in SSM: `/app/healthcare/s3/bucket_name`

- [ ] **Generate Sample Clinical Documents** (`scripts/generate_sample_documents.py`)
  - [ ] Use LLM to generate synthetic clinical documents
  - [ ] Basic tier (20-30 docs per clinic):
    - Patient intake forms
    - Appointment notes
    - Basic lab results
    - Prescription records
  - [ ] Premium tier (50-100 docs per clinic):
    - Diagnostic reports
    - Imaging study reports
    - Specialist consultation notes
    - Complex lab results
  - [ ] Ensure HIPAA-compliant synthetic data (no real PHI)

- [ ] **Upload Documents to S3** (`scripts/upload_documents_to_s3.py`)
  - [ ] Upload to clinic-specific prefixes
  - [ ] Add metadata tags (document_type, date, clinic_id)
  - [ ] Create document inventory manifest per clinic

**Deliverables**:
- S3 bucket with clinic folder structure
- 200-400 synthetic clinical documents
- Document inventory manifests

---

### 3.2 Document Search Tool (Days 3-4)

- [ ] **Create document_search.py** (`prerequisite/lambda/python/document_search.py`)
  - [ ] Implement S3-based document search
  - [ ] Filter by document type, date range, keywords
  - [ ] **Application-level isolation**: Respect S3 prefix from tenant context
    ```python
    # Get tenant context from request
    tenant_info = extract_tenant_info(event)
    s3_prefix = tenant_info['s3_prefix']  # e.g., "basic-tier/clinic-a/"
    
    # List objects with clinic-specific prefix
    response = s3.list_objects_v2(
        Bucket=bucket_name,
        Prefix=s3_prefix,
        MaxKeys=100
    )
    ```
  - [ ] Return document metadata and presigned URLs
  - [ ] Add pagination for large result sets

- [ ] **Test Clinic Isolation**
  - [ ] Test Clinic A user can access Clinic A documents
  - [ ] Test Clinic A user CANNOT access Clinic B documents (empty results)
  - [ ] Verify S3 prefix filtering works correctly

**Deliverables**:
- Document search tool with application-level clinic isolation
- Clinic isolation verified through testing

---

### 3.3 Document Retrieval & Summarization Tools (Days 5-7)

- [ ] **Create document_retrieval.py** (`prerequisite/lambda/python/document_retrieval.py`)
  - [ ] Fetch document content from S3
  - [ ] Parse common formats (TXT, PDF, JSON)
  - [ ] Extract text content for LLM processing
  - [ ] Implement caching for frequently accessed documents
  - [ ] Respect S3 prefix from tenant context (clinic isolation)

- [ ] **Create document_summarization.py** (`prerequisite/lambda/python/document_summarization.py`)
  - [ ] Implement tier-specific summarization:
    - Basic: Nova Micro (fast, cost-effective)
    - Premium: Claude Sonnet 4.5 (high-quality, detailed)
  - [ ] Support single-document and multi-document summarization
  - [ ] Extract key clinical findings
  - [ ] Generate structured summaries

- [ ] **Create web_search.py** (`prerequisite/lambda/python/web_search.py`) - Premium Only
  - [ ] Integrate web search tool (Tavily, Brave Search, or custom)
  - [ ] Configure for medical research and clinical guidelines
  - [ ] Filter results for credibility
  - [ ] This tool will ONLY be registered with premium gateway

- [ ] **Update or Repurpose Existing Tools**
  - [ ] Review existing tools in `prerequisite/lambda/python/`
  - [ ] Repurpose for healthcare context if applicable
  - [ ] Remove gaming/finance-specific tools

- [ ] **Tool Testing**
  - [ ] Test each tool independently
  - [ ] Test tool chain (search → retrieve → summarize)
  - [ ] Verify tier-specific behavior
  - [ ] Verify basic tier cannot access web search (enforced by gateway)
  - [ ] Test clinic isolation (Clinic A can't access Clinic B docs)

**Deliverables**:
- Document retrieval tool
- Document summarization tool with tier differentiation
- Web search tool (premium-only, registered only with premium gateway)
- Tool testing suite
- Clinic isolation verified

---

## Phase 4: Cost Tracking & Monitoring (Week 4: 3-5 days)

**Objective**: Enable complete cost visibility per clinic

### 4.1 Cost Allocation Tags (Day 1)

- [ ] **Enable Cost Allocation Tags** (AWS Billing Console)
  - [ ] Navigate to: Billing → Cost Allocation Tags
  - [ ] Activate tags: `Project`, `Tier`, `Environment`
  - [ ] Wait 24 hours for tags to appear in Cost Explorer
  - [ ] Verify tags visible in Cost Explorer

**Deliverables**:
- Cost allocation tags enabled

---

### 4.2 Cost Reporting Scripts (Days 2-3)

- [ ] **Create Cost Data Collection Script** (`scripts/collect_cost_data.py`)
  - [ ] Query Cost Explorer for model costs by Tier tag
  - [ ] Query CloudWatch Logs for runtime costs by baggage.clinic_id
  - [ ] Query CloudWatch Logs for memory costs by tenant_id
  - [ ] Aggregate costs per clinic and tier

- [ ] **Create Cost Report Generator** (`scripts/generate_cost_report.py`)
  - [ ] Generate monthly cost report per clinic
  - [ ] Break down costs by component:
    - Model invocation costs (Bedrock)
    - Runtime costs (CPU, memory)
    - Memory costs (events, retrievals)
    - API Gateway costs
  - [ ] Calculate total cost per clinic
  - [ ] Generate tier comparison (Basic vs Premium)
  - [ ] Export to CSV format

- [ ] **Create CloudWatch Logs Insights Saved Queries**
  - [ ] Runtime costs per clinic query
  - [ ] Memory costs per clinic query
  - [ ] Combined cost summary query
  - [ ] Save queries for easy access

**Deliverables**:
- Cost data collection script
- Cost report generator
- CloudWatch Logs Insights saved queries

---

### 4.3 Monitoring Dashboard (Days 4-5)

- [ ] **Create CloudWatch Dashboard** ("Healthcare Multi-Tenant Overview")
  - [ ] Add widgets:
    - Agent invocations per clinic (bar chart)
    - Memory usage per clinic (line chart)
    - Model token usage per clinic (stacked area)
    - Error rates per clinic (line chart)
    - Latency percentiles per tier (line chart)
  - [ ] Add filters for date range, tier, clinic
  - [ ] Set up automated refresh

- [ ] **Set Up CloudWatch Alarms**
  - [ ] High error rate per clinic
  - [ ] Unusual cost spike per clinic
  - [ ] Memory usage threshold exceeded
  - [ ] API Gateway throttling events

- [ ] **Test Cost Tracking**
  - [ ] Generate test traffic for multiple clinics
  - [ ] Wait for data to appear in CloudWatch
  - [ ] Run cost report script
  - [ ] Verify per-clinic cost attribution
  - [ ] Document cost tracking methodology

**Deliverables**:
- CloudWatch monitoring dashboard
- CloudWatch alarms configured
- Cost tracking verified and documented

---

## Phase 5: Frontend & Demo Preparation (Week 5: 5-7 days)

**Objective**: Create healthcare-focused UI and demo scenarios

### 5.1 Streamlit UI Refactoring (Days 1-3)

- [ ] **Update Authentication** (`app_modules/auth.py`)
  - [ ] Extend `get_enhanced_user_claims()` to extract clinic info
  - [ ] Display clinic information in sidebar
  - [ ] Add tier-specific badges

- [ ] **Create Clinic-Aware Components** (`app_modules/ui_components.py`)
  - [ ] `render_clinic_header()` - Display clinic branding
  - [ ] `render_document_chat_interface()` - Document-focused chat
  - [ ] `render_clinical_results()` - Structured result display

- [ ] **Update Main App** (`app.py`)
  - [ ] Replace gaming/finance chat with clinical document chat
  - [ ] Add document scope indicator
  - [ ] Implement tier-specific prompt suggestions
  - [ ] Add document type and date filters

**Deliverables**:
- Healthcare-focused Streamlit UI
- Clinic-aware authentication and branding

---

### 5.2 Demo Scenarios (Days 4-5)

- [ ] **Create Demo Scenarios** (`demo/scenarios/`)
  - [ ] Scenario 1: Basic Tier - Family Practice (Clinic A)
    - Query: "Show me recent patient intake forms"
    - Demonstrates: Document search, basic summarization, clinic isolation
  - [ ] Scenario 2: Basic Tier - Urgent Care (Clinic B)
    - Query: "What are common symptoms in recent visits?"
    - Demonstrates: Entity extraction, pattern analysis, rate limiting
  - [ ] Scenario 3: Premium Tier - Multi-specialty Hospital (Hospital A)
    - Query: "Analyze diagnostic trends across departments"
    - Demonstrates: Multi-document analysis, advanced analytics, web search
  - [ ] Scenario 4: Premium Tier - Cardiology Clinic (Clinic E)
    - Query: "Compare treatment outcomes for hypertension patients"
    - Demonstrates: Longitudinal analysis, outcome tracking, premium features
  - [ ] Scenario 5: Isolation Demonstration
    - Show Clinic A user cannot access Clinic B documents
    - Show Basic tier user cannot access Premium features
    - Demonstrate rate limit enforcement

- [ ] **Create Demo Script** (`demo/demo_script.md`)
  - [ ] Step-by-step walkthrough
  - [ ] Talking points for each scenario
  - [ ] Expected outputs
  - [ ] Troubleshooting tips

**Deliverables**:
- 5 comprehensive demo scenarios
- Demo script with talking points

---

### 5.3 End-to-End Testing (Days 6-7)

- [ ] **Integration Testing** (`test/test_e2e.py`)
  - [ ] Test complete user flows for all 8 clinics
  - [ ] Verify authentication and authorization
  - [ ] Test document search and retrieval
  - [ ] Validate memory persistence across sessions
  - [ ] Test error handling and edge cases

- [ ] **Memory Isolation Testing** (`test/test_memory_isolation.py`)
  - [ ] Test same-user access (should succeed)
  - [ ] Test cross-user access within same clinic (should return empty)
  - [ ] Test cross-clinic access (should return empty)
  - [ ] Test cross-tier access (should fail)
  - [ ] Document test results

- [ ] **Performance Testing**
  - [ ] Load testing with concurrent users
  - [ ] Measure latency per tier
  - [ ] Test rate limiting enforcement
  - [ ] Document performance metrics

**Deliverables**:
- Comprehensive end-to-end test suite
- Memory isolation verification
- Performance test results

---

## Phase 6: Final Documentation (Week 6: 2-3 days)

**Objective**: Complete documentation

### 6.1 Documentation (Days 1-3)

- [ ] **Architecture Documentation** (`docs/architecture.md`)
  - [ ] Update architecture diagrams for healthcare
  - [ ] Document multi-tenancy strategy
  - [ ] Explain memory isolation approach
  - [ ] Document cost tracking implementation

- [ ] **Deployment Guide** (`docs/deployment.md`)
  - [ ] Step-by-step deployment instructions
  - [ ] Prerequisites and requirements
  - [ ] Configuration checklist
  - [ ] Troubleshooting guide

- [ ] **User Guide** (`docs/user_guide.md`)
  - [ ] Clinic administrator guide
  - [ ] End-user guide (physicians, nurses)
  - [ ] Feature comparison (Basic vs Premium)
  - [ ] FAQ and common issues

- [ ] **Cost Tracking Guide** (`docs/cost_tracking.md`)
  - [ ] Cost tracking methodology
  - [ ] How to generate cost reports
  - [ ] Sample cost reports
  - [ ] Cost optimization recommendations

**Deliverables**:
- Complete documentation suite

---

## Timeline Summary

| Phase | Duration | Key Deliverables | When Code Changes Happen |
|-------|----------|------------------|--------------------------|
| **Phase 1: Code Refactoring** | 5-7 days | Healthcare code ready | ✅ **BEFORE deployment** |
| **Phase 2: Infrastructure Deployment** | 3-5 days | AWS resources deployed | Uses refactored code |
| **Phase 3: Clinical Tools & S3** | 5-7 days | Document processing tools | After deployment |
| **Phase 4: Cost Tracking** | 3-5 days | Cost reporting | After deployment |
| **Phase 5: Frontend & Demo** | 5-7 days | UI and demo scenarios | After deployment |
| **Phase 6: Documentation** | 2-3 days | Complete docs | After deployment |

**Total: 5-6 weeks (25-37 days)**

---

## Key Workflow Principles

### ✅ Correct Workflow (This Roadmap)

1. **Week 1**: Refactor ALL code for healthcare (JWT, agents, context, prompts)
2. **Week 2**: Run `deploy.sh` with healthcare-ready code
3. **Week 3+**: Build on deployed infrastructure (tools, UI, testing)

### ❌ Wrong Workflow (Avoid)

1. Deploy with gaming/finance code
2. Try to update code after agents are running
3. Redeploy to pick up changes

### Why This Matters

- **Code changes BEFORE deployment** ensures healthcare context is baked in from the start
- **No redeployment needed** after initial deployment
- **Agents understand clinic context** from first invocation
- **Memory isolation works** from day one
- **Cost tracking accurate** from first request

### Critical Success Factors

1. **Complete Phase 1 BEFORE running deploy.sh**
2. **Test code changes locally** before deployment
3. **Verify JWT parsing** extracts clinic_id correctly
4. **Ensure baggage is set** in entrypoint functions
5. **Update ALL configuration files** for healthcare naming

### Risk Mitigation

- **Code Review**: Review all Phase 1 changes before deployment
- **Local Testing**: Test JWT parsing and context management locally
- **Incremental Deployment**: Deploy infrastructure in stages (Phase 2)
- **Rollback Plan**: Keep gaming/finance code in separate branch
- **Documentation**: Document all code changes for future reference

**Follows**: `deploy.sh` lines 38-43

- [ ] **Create Inference Profiles** (`scripts/create_inference_profiles.py`)
  - [ ] Update script for healthcare:
    - Profile names: `healthcare-basic-profile`, `healthcare-premium-profile`
    - Model IDs:
      - Basic: `us.amazon.nova-micro-v1:0`
      - Premium: `us.anthropic.claude-sonnet-4-v2:0`
    - Tags: `Project=HealthcareDemo`, `Tier=Basic/Premium`, `Environment=demo`
  - [ ] Run script: `python scripts/create_inference_profiles.py`
  - [ ] Verify profiles created in Bedrock console
  - [ ] Verify ARNs stored in SSM:
    - `/app/healthcare/inference_profiles/basic_arn`
    - `/app/healthcare/inference_profiles/premium_arn`

- [ ] **Update Deployment Configuration** (`scripts/configure_deployment.py`)
  - [ ] Update script to use `/app/healthcare/*` SSM paths
  - [ ] Run: `python scripts/configure_deployment.py`
  - [ ] Verify agent files updated with correct profile ARNs
  - [ ] Verify `.bedrock_agentcore.yaml` generated

- [ ] **List and Verify SSM Parameters** (`scripts/list_ssm_parameters.sh`)
  - [ ] Run: `./scripts/list_ssm_parameters.sh`
  - [ ] Verify all healthcare parameters present

**Deliverables**:
- 2 inference profiles with healthcare models
- Updated agent configuration files
- Complete SSM parameter inventory

---

### 1.4 AgentCore Gateway & Credentials (Day 2 - Afternoon)

**Follows**: `deploy.sh` lines 47-52

- [ ] **Create AgentCore Gateway** (`scripts/agentcore_gateway.py`)
  - [ ] Update script for healthcare naming
  - [ ] Run: `python scripts/agentcore_gateway.py create --name healthcare-gw`
  - [ ] Verify gateway created and active
  - [ ] Store gateway URL in SSM: `/app/healthcare/agentcore/gateway_url`

- [ ] **Setup Cognito Credential Provider** (`scripts/cognito_credentials_provider.py`)
  - [ ] Update script for healthcare naming
  - [ ] Run: `python scripts/cognito_credentials_provider.py create --name healthcare-gateways`
  - [ ] Verify credential provider active

- [ ] **Test Gateway** (`test/test_gateway.py`)
  - [ ] Update test for healthcare context
  - [ ] Run: `python test/test_gateway.py --prompt "Search for patient intake forms"`
  - [ ] Verify gateway responds correctly

**Deliverables**:
- AgentCore Gateway deployed
- Cognito credential provider configured
- Gateway integration tested

---

### 1.5 Memory Resources & Observability (Day 3)

**Follows**: `deploy.sh` lines 54-61 (adapted for healthcare)

- [ ] **Create Memory Resources** (`scripts/agentcore_memory.py`)
  - [ ] Update script for healthcare with namespace templates
  - [ ] Create basic tier memory:
    ```bash
    python scripts/agentcore_memory.py create \
      --name healthcare-basic-memory \
      --namespaces "clinic/{actorId}/facts/{sessionId}" "clinic/{actorId}/preferences" \
      --expiry-days 90
    ```
  - [ ] Create premium tier memory:
    ```bash
    python scripts/agentcore_memory.py create \
      --name healthcare-premium-memory \
      --namespaces "clinic/{actorId}/insights/{sessionId}" "clinic/{actorId}/preferences" "clinic/{actorId}/analytics" \
      --expiry-days 180
    ```
  - [ ] Verify memory resources ACTIVE
  - [ ] Store memory IDs in SSM

- [ ] **Enable Memory Observability** (NEW - Critical for cost tracking)
  - [ ] Create script: `scripts/setup_memory_observability.py`
  - [ ] Run for both memory resources
  - [ ] Verify CloudWatch log groups created
  - [ ] Verify X-Ray traces enabled

- [ ] **Test Memory Functionality** (`test/test_memory.py`)
  - [ ] Update tests for healthcare context
  - [ ] Run memory tests
  - [ ] Verify memory isolation per actor_id

**Deliverables**:
- 2 Memory resources with namespace templates
- Memory observability enabled
- Memory functionality tested

---

### 1.6 Agent Configuration & Deployment (Day 4)

**Follows**: `deploy.sh` lines 63-77

- [ ] **Get Runtime Role from SSM** (`deploy.sh` lines 63-68)
  - [ ] Extract runtime IAM role ARN
  - [ ] Verify role has necessary permissions

- [ ] **Configure Basic Tier Agent** (`deploy.sh` lines 70-73)
  - [ ] Run:
    ```bash
    agentcore configure --entrypoint main.py \
      -er "$RUNTIME_ROLE" \
      --name healthcare-basic
    ```
  - [ ] Verify `.agentcore.json` created

- [ ] **Configure Premium Tier Agent** (`deploy.sh` lines 75-77)
  - [ ] Run:
    ```bash
    agentcore configure --entrypoint main_premium.py \
      -er "$RUNTIME_ROLE" \
      --name healthcare-premium
    ```
  - [ ] Verify `.agentcore.json` created

- [ ] **Clean Up Old Config** (`deploy.sh` line 79)
  - [ ] Remove: `rm -f .agentcore.yaml`

**Deliverables**:
- 2 AgentCore agents configured
- Agent configuration files ready

---

### 1.7 Cognito User Setup (Day 5)

**NEW**: Required for healthcare multi-clinic testing

- [ ] **Add Custom Attributes to Cognito**
  - [ ] Add `custom:clinic_id` attribute to user pool
  - [ ] Add `custom:role` attribute (physician, nurse, admin)

- [ ] **Create Test Users for 8 Clinics**
  - [ ] Basic tier users (4 clinics)
  - [ ] Premium tier users (4 clinics)
  - [ ] Verify JWT tokens include custom attributes

- [ ] **Create User Management Script** (`scripts/create_test_users.py`)
  - [ ] Automate user creation
  - [ ] Generate credentials document

**Deliverables**:
- Cognito user pool with custom attributes
- 8 test users (one per clinic)
- User credentials document

---

## Phase 2: Healthcare Code Adaptation (Week 2: 5-7 days)

**Objective**: Transform gaming/finance agent code to healthcare clinical document processing

### 2.1 JWT Parsing & Tenant Context (Day 1)

- [ ] **Update JWT Utilities** (`agent_config/jwt_utils.py`)
  - [ ] Extract `custom:tenant_id`, `custom:clinic_id`, `cognito:username`
  - [ ] Construct hierarchical `actor_id`
  - [ ] Return complete tenant info dict

- [ ] **Enhanced Context Management** (`agent_config/context.py`)
  - [ ] Add clinic-specific context variables
  - [ ] Implement getter/setter methods

**Deliverables**:
- Enhanced JWT parsing
- Extended context management

---

### 2.2 Agent Entrypoint Updates (Day 2)

- [ ] **Update main.py and main_premium.py**
  - [ ] Import OpenTelemetry baggage
  - [ ] Set baggage at entrypoint (3 lines)
  - [ ] Initialize MemorySessionManager
  - [ ] Create memory session with actor_id

- [ ] **Test Baggage Propagation**
  - [ ] Verify baggage in CloudWatch Logs

**Deliverables**:
- Updated entrypoints with baggage
- Verified baggage propagation

---

### 2.3 Agent Class Refactoring (Days 3-4)

- [ ] **Update agent_config/agent.py**
  - [ ] Replace gaming console prompt with healthcare prompt
  - [ ] Update tool list for healthcare
  - [ ] Keep inference profile mapping

- [ ] **Update agent_config_premium/agent.py**
  - [ ] Update for premium healthcare capabilities
  - [ ] Add premium-only tools

**Deliverables**:
- Refactored agent classes
- Healthcare-specific prompts

---

### 2.4 S3 Document Structure Setup (Day 5)

- [ ] **Create S3 Bucket for Documents**
  - [ ] Create bucket with clinic folder structure
  - [ ] Configure bucket policies

- [ ] **Generate Sample Clinical Documents**
  - [ ] Use LLM to generate synthetic documents
  - [ ] Basic tier: 20-30 docs per clinic
  - [ ] Premium tier: 50-100 docs per clinic

- [ ] **Upload Documents to S3**
  - [ ] Upload to clinic-specific prefixes
  - [ ] Add metadata tags

**Deliverables**:
- S3 bucket with documents
- 200-400 synthetic clinical documents

---

## Phase 3: Clinical Document Tools (Week 3: 5-7 days)

**Objective**: Implement healthcare-specific tools

### 3.1 Document Search Tool (Days 1-2)

- [ ] **Create document_search.py**
  - [ ] Implement S3-based search
  - [ ] Respect clinic isolation

- [ ] **Integrate with MCP Gateway**
  - [ ] Register tool
  - [ ] Test invocation

**Deliverables**:
- Document search tool

---

### 3.2 Document Retrieval & Summarization (Days 3-4)

- [ ] **Create document_retrieval.py**
  - [ ] Fetch from S3
  - [ ] Parse formats

- [ ] **Create document_summarization.py**
  - [ ] Tier-specific summarization
  - [ ] Extract clinical findings

**Deliverables**:
- Retrieval and summarization tools

---

### 3.3 Premium-Only Tools (Days 5-7)

- [ ] **Web Search Integration**
  - [ ] Configure for medical research

- [ ] **Multi-Document Analysis**
  - [ ] Analyze multiple documents
  - [ ] Identify trends

**Deliverables**:
- Premium-exclusive tools

---

## Phase 4: Cost Tracking & Monitoring (Week 4: 3-5 days)

**Objective**: Enable cost visibility per clinic

### 4.1 Cost Allocation Tags (Day 1)

- [ ] **Enable in AWS Billing Console**
  - [ ] Activate tags
  - [ ] Wait 24 hours

**Deliverables**:
- Cost allocation tags enabled

---

### 4.2 Cost Reporting Scripts (Days 2-3)

- [ ] **Create collect_cost_data.py**
  - [ ] Query Cost Explorer
  - [ ] Query CloudWatch Logs

- [ ] **Create generate_cost_report.py**
  - [ ] Generate monthly reports
  - [ ] Export to CSV

**Deliverables**:
- Cost reporting scripts

---

### 4.3 Monitoring Dashboard (Days 4-5)

- [ ] **Create CloudWatch Dashboard**
  - [ ] Add widgets for metrics
  - [ ] Set up alarms

- [ ] **Test Cost Tracking**
  - [ ] Generate test traffic
  - [ ] Verify attribution

**Deliverables**:
- Monitoring dashboard
- Cost tracking verified

---

## Phase 5: Frontend & Demo (Week 5: 5-7 days)

**Objective**: Create UI and demo scenarios

### 5.1 Streamlit UI Refactoring (Days 1-3)

- [ ] **Update Authentication**
  - [ ] Extract clinic info
  - [ ] Display in sidebar

- [ ] **Create Clinic Components**
  - [ ] Clinic header
  - [ ] Document chat interface
  - [ ] Clinical results display

**Deliverables**:
- Healthcare-focused UI

---

### 5.2 Demo Scenarios (Days 4-5)

- [ ] **Create 5 Demo Scenarios**
  - [ ] Basic tier scenarios (2)
  - [ ] Premium tier scenarios (2)
  - [ ] Isolation demonstration (1)

- [ ] **Create Demo Script**
  - [ ] Step-by-step walkthrough
  - [ ] Talking points

**Deliverables**:
- Demo scenarios and script

---

### 5.3 End-to-End Testing (Days 6-7)

- [ ] **Integration Testing**
  - [ ] Test all 8 clinics
  - [ ] Verify isolation

- [ ] **Memory Isolation Testing**
  - [ ] Test cross-user access
  - [ ] Test cross-clinic access

- [ ] **Performance Testing**
  - [ ] Load testing
  - [ ] Rate limiting

**Deliverables**:
- Complete test suite

---

## Phase 6: Final Deployment & Documentation (Week 6: 3-5 days)

**Objective**: Deploy and document

### 6.1 Production Deployment (Days 1-2)

- [ ] **Run Full Deployment**
  - [ ] Execute: `./deploy.sh`
  - [ ] Monitor progress

- [ ] **Launch Services**
  - [ ] Run: `agentcore launch`
  - [ ] Run: `streamlit run app.py`

**Deliverables**:
- Production deployment

---

### 6.2 Documentation (Days 3-5)

- [ ] **Create Documentation**
  - [ ] Architecture docs
  - [ ] Deployment guide
  - [ ] User guide
  - [ ] Cost tracking guide

**Deliverables**:
- Complete documentation

---

## Timeline Summary

| Phase | Duration | Key Deliverables |
|-------|----------|------------------|
| Phase 1: Infrastructure | 5-7 days | AWS resources, agents configured |
| Phase 2: Code Adaptation | 5-7 days | Healthcare agent code |
| Phase 3: Clinical Tools | 5-7 days | Document processing tools |
| Phase 4: Cost Tracking | 3-5 days | Cost reporting |
| Phase 5: Frontend & Demo | 5-7 days | UI and demo scenarios |
| Phase 6: Deployment & Docs | 3-5 days | Production deployment |

**Total: 6 weeks (30-42 days)**
