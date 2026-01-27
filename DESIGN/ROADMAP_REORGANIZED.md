# Healthcare Multi-Tenancy Development Roadmap (Reorganized)

**Based on deploy.sh deployment flow**

This roadmap follows a proper development workflow: **Code changes FIRST, then deployment**. The code refactoring happens before running `deploy.sh` to ensure healthcare-specific logic is in place during infrastructure setup.

## Phase 1: Code Refactoring & Preparation (Week 1: 5-7 days)

**Objective**: Refactor existing gaming/finance code to healthcare BEFORE deployment

**Critical**: All code changes must be completed before running `deploy.sh`

### 1.1 Environment Setup & Configuration Updates (Day 1)

- [x] **Update All Configuration Files** (BEFORE deployment)
  
  - [x] Update `scripts/prereq.sh`:
    - Change default bucket name to `healthcare`
    - Change stack names: `HealthcareStackInfra`, `HealthcareStackCognito`
  - [x] Update CloudFormation templates in `prerequisite/`:
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
  - [x] Update `prerequisite/lambda/python/api_gateway_lambda.py`:
    - Update `extract_tenant_info()` to extract `clinic_id` from JWT:
      ```python
      clinic_id = claims.get('custom:clinic_id', 'demo-clinic')
      ```
    - Add `clinic_id` to payload forwarded to AgentCore
    - Add `X-Clinic-ID` response header
  - [x] Update `scripts/create_inference_profiles.py`:
    - Profile names: `healthcare-basic-profile`, `healthcare-premium-profile` (2 tier-level profiles)
    - Model IDs:
      - Basic: `us.amazon.nova-micro-v1:0`
      - Premium: `us.amazon.nova-2-lite-v1:0` (with built-in web grounding)
    - Tags: `Project=HealthcareDemo`, `Tier=Basic/Premium`, `Environment=demo`
    - SSM paths: `/app/healthcare/inference_profiles/basic_arn`, `premium_arn`
  - [x] Update `scripts/configure_deployment.py`:
    - Change SSM parameter paths to `/app/healthcare/*`
    - Update regex patterns for healthcare naming
  - [x] Update `scripts/agentcore_gateway.py`:
    - Support creating 2 gateways: `healthcare-basic-gw`, `healthcare-premium-gw`
    - Each gateway will have tier-specific tools
    - Added `create-all` and `delete-all` convenience commands
  - [x] Update `scripts/cognito_credentials_provider.py`:
    - Change SSM parameter paths to `/app/healthcare/*`
    - Single shared credential provider for both gateways
    - Updated naming: `healthcare-cognito-provider`
  - [x] Update `scripts/agentcore_memory.py`:
    - Add namespace template support
    - Default names: `healthcare-basic-memory`, `healthcare-premium-memory`
- [x] Update `deploy.sh`:
    - Change `BUCKET_NAME=customersupport` → `BUCKET_NAME=healthcare`
    - Change agent names: `healthcare-basic`, `healthcare-premium`
    - Update all references to `customersupport` → `healthcare`
    - Use `create-all` command for gateways
    - Add memory observability setup (after memory creation)
    - Add Cognito user creation (after agent configuration)
    - Add S3 document bucket setup (optional)
    - Update final success message with healthcare context

**Deliverables**: 
- All configuration files updated for healthcare 
- Cognito custom attributes defined in CloudFormation
- API Gateway Lambda proxy updated to extract clinic_id
- Knowledge base script updated for healthcare
- 2 tier-level inference profiles configured (not 8 clinic-level)

---

### 1.2 JWT Parsing & Tenant Context (Day 2)

**Critical**: Update JWT parsing BEFORE deployment so agents understand clinic context

- [x] **Update JWT Utilities** (`agent_config/jwt_utils.py`, `agent_config_premium/jwt_utils.py`)
  - [x] Extract `custom:tenant_id` (tier: basic/premium)
  - [x] Extract `custom:clinic_id` (clinic identifier)
  - [x] Extract `cognito:username` (user identifier)
  - [x] Construct hierarchical `actor_id`: `"{tier}-{clinic_id}-{user_id}"`
  - [x] Return complete tenant info dict:
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
  - [x] Add comprehensive logging
  - [x] Implement fallback for missing claims

- [x] **Enhanced Context Management** (`agent_config/context.py`, `agent_config_premium/context.py`)
  - [x] Add `_clinic_id` class variable and context var
  - [x] Add `_tenant_key` (combined tier-clinic identifier)
  - [x] Add `_s3_prefix` (document scope prefix)
  - [x] Add `_actor_id` (memory isolation identifier)
  - [x] Implement getter/setter methods for all new context vars
  - [x] Add fallback logic for missing context values

**Deliverables**:
- Enhanced JWT parsing with clinic extraction ✅
- Extended context management for clinic isolation ✅
- Code ready for deployment (NOT deployed yet) ✅

---

### 1.3 Agent Entrypoint Updates (Day 3)

**Critical**: Add OpenTelemetry baggage and memory integration BEFORE deployment

- [x] **Update main.py (Basic Tier)**
  - [x] Import OpenTelemetry baggage: `from opentelemetry import baggage, context`
  - [x] Update `@app.entrypoint` function:
    - [x] Extract tenant info from payload (forwarded by API Gateway Lambda)
    - [x] Set OpenTelemetry baggage (4 lines):
      ```python
      ctx = baggage.set_baggage("tenant_id", tenant_info['tenant_key'])
      ctx = baggage.set_baggage("tier", tenant_info['tier'], context=ctx)
      ctx = baggage.set_baggage("clinic_id", tenant_info['clinic_id'], context=ctx)
      ctx = baggage.set_baggage("actor_id", tenant_info['actor_id'], context=ctx)
      context.attach(ctx)
      ```
    - [x] Initialize MemorySessionManager with tier-specific memory
    - [x] Create memory session with user-specific actor_id
    - [x] Pass memory session to agent task

- [x] **Update main_premium.py (Premium Tier)**
  - [x] Same changes as main.py
  - [x] Ensure premium memory ID used (`healthcare-premium-memory`)
  - [x] Verify premium-specific features enabled

- [x] **Update API Gateway Lambda**
  - [x] Extract `user_id` from `cognito:username` JWT claim
  - [x] Forward `tenant_id`, `clinic_id`, `user_id` in payload to AgentCore
  - [x] Add `X-User-ID` to response headers

**Deliverables**:
- Updated agent entrypoints with baggage and memory integration ✅
- Payload-based tenant extraction (consistent with existing pattern) ✅
- API Gateway Lambda enhanced to forward user_id ✅
- Code ready for deployment (NOT deployed yet) ✅

---

### 1.4 Agent Class Refactoring (Days 4-5)

**Critical**: Replace gaming/finance logic with healthcare BEFORE deployment

- [x] **Update agent_config/agent.py (Basic Tier)**
  - [x] Replace gaming console system prompt with healthcare prompt with tenant context
  - [x] Update tool list for healthcare (placeholder tools for now)
  - [x] Remove gaming console-specific tools
  - [x] Keep inference profile mapping logic (already correct)
  - [x] Update MCP gateway headers to include clinic_id, s3_prefix

- [x] **Update agent_config_premium/agent.py (Premium Tier)**
  - [x] Update system prompt for premium healthcare capabilities with web search
  - [x] Add Nova 2 web grounding configuration via `tool_config`
  - [x] Configure BedrockModel with `systemTool: nova_grounding`
  - [x] Update tool descriptions for clinical context
  - [x] Update MCP gateway headers to include clinic_id, s3_prefix

- [x] **Update agent_task.py files (Both Tiers)**
  - [x] Pass all tenant context parameters to agent initialization
  - [x] Include clinic_id, user_id, role, s3_prefix in agent creation
  - [x] Add logging for tenant context

- [x] **Verify Strands Framework Configuration**
  - [x] Custom retrieval tool with metadata filtering configured:
    - [x] Created `agent_config/tools/retrieve_clinic_documents.py` with `@tool` decorator
    - [x] Created `agent_config_premium/tools/retrieve_clinic_documents.py` with `@tool` decorator
    - [x] Uses Bedrock Agent Runtime `retrieve()` API with clinic_id filtering
    - [x] Replaces built-in `strands_tools.retrieve` for proper tenant isolation
  - [x] Knowledge Base integration via custom tool:
    - [x] KB IDs set via environment variable in main.py and main_premium.py
    - [x] Retrieved from SSM: `/app/customersupport/knowledge_base/knowledge_base_id`
    - [x] Premium uses: `/app/customersupport/premium_knowledge_base/knowledge_base_id`
  - [x] Tenant isolation enforced via:
    - [x] **Vector-level filtering**: Metadata filter on clinic_id in KB query
    - [x] S3 prefix in KB data sources (basic-tier/clinic-a/, premium-tier/hospital-a/)
    - [x] MCP gateway headers include clinic_id for Lambda invocation
    - [x] System prompts explicitly state document scope restrictions
  
  **Note**: Custom `retrieve_clinic_documents` tool provides vector-level isolation via metadata filtering, ensuring each clinic can only access their documents at the Knowledge Base query level.

**Deliverables**:
- Refactored agent classes with healthcare prompts ✅
- Updated tool configurations ✅
- Strands framework configured for KB integration ✅
- Tenant context properly passed to agents ✅
- Code ready for deployment (NOT deployed yet) ✅

- [x] **Update agent_config_premium/agent.py (Premium Tier)**
  - [x] Update system prompt for premium healthcare capabilities with web search
  - [x] Add Nova 2 web grounding configuration via `tool_config`
  - [x] Configure BedrockModel with `systemTool: nova_grounding`
  - [x] Update tool descriptions for clinical context
  - [x] Update MCP gateway headers to include clinic_id, s3_prefix

- [x] **Update agent_task.py files (Both Tiers)**
  - [x] Pass all tenant context parameters to agent initialization
  - [x] Include clinic_id, user_id, role, s3_prefix in agent creation
  - [x] Add logging for tenant context

  
  **Note**: Custom `retrieve_clinic_documents` tool provides vector-level isolation via metadata filtering, ensuring each clinic can only access their documents at the Knowledge Base query level.

**Deliverables**:
- Refactored agent classes with healthcare prompts ✅
- Updated tool configurations ✅
- Strands framework configured for KB integration 
- Tenant context properly passed to agents ✅
- Code ready for deployment (NOT deployed yet) ✅

---

### 1.5 Create Memory Observability Script (Day 6)

**Critical**: Create script BEFORE deployment so it's ready to run after memory resources are created

- [x] **Create scripts/setup_memory_observability.py**
  - [x] Implement function to enable observability for Memory resources
  - [x] Create CloudWatch log groups
  - [x] Configure delivery sources (APPLICATION_LOGS, TRACES)
  - [x] Configure delivery destinations (CloudWatch Logs, X-Ray)
  - [x] Create deliveries to connect sources to destinations
  - [x] Accept memory IDs as parameters
  - [x] Add error handling and verification
  - [x] Add `enable-all` convenience command for both tiers
  - [x] Add `verify` and `verify-all` commands to check configuration

- [x] **Update deploy.sh**
  - [x] Add memory observability setup after memory creation
  - [x] Add verification step to ensure proper configuration

**Deliverables**:
- Memory observability script ready ✅
- Script integrated into deploy.sh ✅
- Scripts NOT executed yet (will run during deployment) ✅

**Note**: Test user creation moved to Phase 2.5 (after agent configuration)

---

### 1.6 Update Knowledge Base Script (Day 7)

**Critical**: Update KB script to use healthcare naming BEFORE deployment

- [x] **Update prerequisite/knowledge_base.py**
  - [x] Change KB names: `healthcare-basic-kb`, `healthcare-premium-kb`
  - [x] Update S3 data source paths for healthcare documents
  - [x] Update SSM parameter paths: `/app/healthcare/knowledge_base/*`
  - [x] Update descriptions for healthcare context

**Deliverables**:
- Knowledge base script updated for healthcare
- Code ready for deployment

--

## Phase 2: Clinical Document Tools & S3 Setup (Week 3: 5-7 days)

**Objective**: Implement healthcare-specific tools and document storage

### 2.1 S3 Document Structure Setup (Days 1-2)

- [x] **Create Document Generation Script** (`scripts/generate_healthcare_documents.py`)
  - [x] Use Claude Sonnet 4.5 to generate synthetic clinical documents
  - [x] Basic tier (24-28 docs per clinic, ~100 total):
    - Patient intake forms
    - Appointment notes
    - Basic lab results
    - Prescription records
  - [x] Premium tier (25-30 docs per clinic, ~113 total):
    - Diagnostic reports
    - Imaging study reports
    - Specialist consultation notes
    - Complex lab results
  - [x] Ensure HIPAA-compliant synthetic data (no real PHI)
  - [x] Save to local `prerequisite/basic-documents/` and `prerequisite/premium-documents/`
  - [x] Idempotent: checks if documents exist before generating

- [x] **S3 Upload Handled by Knowledge Base Script**
  - [x] Existing `knowledge_base.py` already uploads documents to S3
  - [x] Uses `upload_directory()` method to upload from local paths
  - [x] Creates S3 bucket with proper structure during KB creation
  - [x] No separate upload script needed

**Deliverables**:
- ✅ Document generation script created (~213 synthetic documents)
- ✅ Local folder structure matches S3 structure
- ✅ S3 upload integrated into existing Knowledge Base workflow

---

### 2.2 Healthcare Context Tools (Days 3-4)

**Note**: Custom retrieval tool with metadata filtering provides vector-level tenant isolation for Knowledge Base queries.


- [x] **Create retrieve_clinic_documents.py** (`agent_config/tools/retrieve_clinic_documents.py` and `agent_config_premium/tools/retrieve_clinic_documents.py`)
  - [x] Implement custom tool using `@tool` decorator (runs in agent process, not Lambda)
  - [x] Accept parameters: query, clinic_id, max_results
  - [x] Use Bedrock Agent Runtime `retrieve()` API with vectorSearchConfiguration filter
  - [x] Filter by clinic_id metadata: `{'equals': {'key': 'clinic_id', 'value': clinic_id}}`
  - [x] Format results with content from knowledge base
  - [x] Add error handling and logging
  - [x] **Security**: Vector-level isolation ensures clinic cannot access other clinics' documents
  - [x] Integrated into agent.py with clinic_id wrapper function
  - [x] Updated system prompts to reference `retrieve_clinic_documents`
  - [x] Set KNOWLEDGE_BASE_ID environment variable in main.py and main_premium.py

- [x] **Create patient_context.py** (`prerequisite/lambda/python/patient_context.py`)
  - [x] Create DynamoDB table: `healthcare-patient-metadata` via infrastructure.yaml
  - [x] Generate synthetic patient metadata based on clinic profiles (see `DESIGN/clinic-profiles.md`) and integrate this step into the deploy.sh so the end user deployment flow isn't interrupted. You can refer to /design/deployment-integration-plan.md to see a related example
  - [x] Implement Lambda function for structured patient lookup
  - [x] Return patient metadata:
    ```python
    {
        "patient_id": "P12345",
        "age": 45,
        "conditions": ["hypertension", "diabetes"],
        "allergies": ["penicillin"],
        "last_visit": "2024-12-15",
        "assigned_provider": "Dr. Smith",
        "clinic_id": "clinic-a"  # For isolation
    }
    ```
  - [x] **Application-level isolation**: Filter by clinic_id from tenant context
  - [x] Add pagination for patient lists

- [x] **Create clinic_config.py** (`prerequisite/lambda/python/clinic_config.py`)
  - [x] Create DynamoDB table: `healthcare-clinic-config` via infrastructure.yaml
  - [x] Populate clinic configurations from `DESIGN/clinic-profiles.md` and integrate this step into the deploy.sh so the end user deployment flow isn't interrupted
  - [x] Implement Lambda function for clinic settings lookup
  - [x] Return clinic configuration:
    ```python
    {
        "clinic_id": "clinic-a",
        "specialty": "family-practice",
        "available_services": ["primary-care", "urgent-care"],
        "operating_hours": "8am-6pm",
        "providers": ["Dr. Smith", "Nurse Lee"],
        "tier": "basic"
    }
    ```
  - [x] Used by agent to understand clinic context and capabilities

**Deliverables**:
- Custom retrieval tool implemented with `@tool` decorator ✅
- Vector-level isolation via metadata filtering ✅
- Tool integrated into both agent.py files ✅
- System prompts updated ✅
- Patient context tool with clinic isolation ✅
- Clinic configuration tool ✅
- DynamoDB tables with synthetic data from clinic profiles ✅
- Context tools integrated into deployment flow ✅
- Data population script (`scripts/populate_healthcare_data.py`) ✅

**Note**: Custom retrieval tool runs directly in agent process (not Lambda) - no gateway registration needed for this tool.

---

### 2.3 Gateway Tool Registration (Day 5)

**Note**: Web search capability is now built into Nova 2 via native web grounding - no separate Lambda tool needed!

- [x] **Update Lambda Function Handler**
  - [x] Refactored `lambda_function.py` to route to healthcare tools
  - [x] Removed gaming/finance tool routing
  - [x] Added proper tenant context extraction from headers
  - [x] Routes to `patient_context` and `clinic_config` handlers

- [x] **Verify API Specification**
  - [x] `api_spec.json` already contains correct tool schemas
  - [x] patient_context: Patient metadata with list/single lookup
  - [x] clinic_config: Clinic configuration retrieval
  - [x] Both tools support clinic isolation via headers

- [x] **Verify Agent System Prompts**
  - [x] Basic tier agent already references all tools correctly
  - [x] Premium tier agent includes web grounding capability
  - [x] Both agents have proper security rules documented
  - [x] Tool descriptions match API spec

- [x] **Create Tool Testing Suite**
  - [x] Created `test/test_healthcare_tools.py`
  - [x] Supports testing both basic and premium tiers
  - [x] Includes verification command to check tool registration
  - [x] Includes interactive query command for manual testing
  - [x] Tests clinic isolation and tenant context

- [ ] **Deploy and Test** (Ready for Phase 3 deployment)
  - [ ] Run `deploy.sh` to create gateways with tools
  - [ ] Verify tool registration: `python test/test_healthcare_tools.py verify`
  - [ ] Run comprehensive tests: `python test/test_healthcare_tools.py test`
  - [ ] Test interactive queries: `python test/test_healthcare_tools.py query --tier basic --prompt "What services are available?"`

**Deliverables**:
- ✅ Lambda handler updated for healthcare tools
- ✅ API spec verified and correct
- ✅ Agent system prompts verified
- ✅ Comprehensive tool testing suite created
- ⏳ Ready for deployment in Phase 3

**Key Advantage**: 
- Custom retrieval tool provides **defense in depth** - combines S3 prefix isolation with query-time metadata filtering
- Nova 2's built-in web grounding eliminates need for external API integration
- Tools are registered automatically during gateway creation via `api_spec.json`


---

## Phase 3: Infrastructure Deployment (Week 2: 3-5 days)

**Objective**: Deploy healthcare infrastructure using refactored code

**Now we run deploy.sh with healthcare-ready code**

### 3.1 AWS Infrastructure Deployment (Day 1)

**Follows**: `deploy.sh` lines 34-36 → `scripts/prereq.sh`

- [x] **Run Infrastructure Setup**
  - [x] Execute: `chmod +x scripts/prereq.sh && ./scripts/prereq.sh`
  - [x] Creates S3 bucket: `healthcare-{account-id}`
  - [x] Deploys CloudFormation stacks:
    - `HealthcareStackInfra` (IAM roles, ECR repos)
    - `HealthcareStackCognito` (User pool, app client)
    - `HealthcareStackApiGW`
  - [x] Creates Knowledge Bases: `healthcare-basic-kb`, `healthcare-premium-kb`
  - [x] Stores all resource IDs in SSM: `/app/healthcare/*`

- [x] **Verify Infrastructure**
  - [x] Check CloudFormation stacks: `COMPLETE` status
  - [x] Check S3 bucket created
  - [x] Check Knowledge Bases: `ACTIVE` status
  - [x] List SSM parameters: `./scripts/list_ssm_parameters.sh`

**Deliverables**:
- S3 bucket with Lambda code
- 2 CloudFormation stacks deployed
- 3 Knowledge Bases created
- SSM parameters populated

---

### 3.2 Inference Profiles & Configuration (Day 2 - Morning)

**Follows**: `deploy.sh` lines 38-43

- [x] **Create Inference Profiles**
  - [x] Run: `python scripts/create_inference_profiles.py`
  - [x] Creates:
    - `healthcare-basic-profile` with Nova Micro
    - `healthcare-premium-profile` with Nova 2 Lite (with web grounding)
  - [x] Stores ARNs in SSM: `/app/healthcare/inference_profiles/*`

- [x] **Update Deployment Configuration**
  - [x] Run: `python scripts/configure_deployment.py`
  - [x] Updates agent files with profile ARNs
  - [x] Generates `.bedrock_agentcore.yaml`

- [ ] **Verify Configuration**
  - [ ] Run: `./scripts/list_ssm_parameters.sh`
  - [ ] Verify all healthcare parameters present
  - [ ] Check agent files have correct ARNs

**Deliverables**:
- 2 inference profiles created
- Agent configuration files updated
- SSM parameters verified

---

### 3.3 AgentCore Gateway & Credentials (Day 2 - Afternoon)

**Follows**: `deploy.sh` lines 47-52 (adapted for 2 gateways)

- [x] **Create AgentCore Gateways** (2 gateways for tier-specific tools)
  - [x] Create basic tier gateway:
    ```bash
    python scripts/agentcore_gateway.py create --name healthcare-basic-gw
    ```
  - [x] Create premium tier gateway:
    ```bash
    python scripts/agentcore_gateway.py create --name healthcare-premium-gw
    ```
  - [x] Verify both gateways created and active
  - [x] Store gateway URLs in SSM:
    - `/app/healthcare/agentcore/basic_gateway_url`
    - `/app/healthcare/agentcore/premium_gateway_url`

- [x] **Setup Cognito Credential Provider** (1 shared provider for both gateways)
  - [x] Create single credential provider shared by both tiers:
    ```bash
    python scripts/cognito_credentials_provider.py create --name healthcare-cognito-provider
    ```
  - [x] Links Cognito to both basic and premium AgentCore gateways
  - [x] Verify credential provider is active
  - [x] Note: Single Cognito User Pool with custom JWT claims (`custom:tenant_id`, `custom:clinic_id`) handles tenant differentiation

- [x] **Register Tools with Gateways**
  - [x] Register basic tools with basic gateway:
    - patient_context (Lambda target)
    - clinic_config (Lambda target)
  - [x] Register premium tools with premium gateway:
    - patient_context (Lambda target)
    - clinic_config (Lambda target)
    - **Web grounding enabled via Nova 2 model configuration** - No Lambda needed!
  - [x] Use `scripts/agentcore_gateway.py` target registration functionality
  - [x] Verify tool registration for both gateways

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

### 3.4 Memory Resources & Observability (Day 3)

**Follows**: `deploy.sh` lines 54-61 (adapted)

- [x] **Create Memory Resources**
  - [x] Create basic and premium memory resources
  - [x] Verify memory resources: `ACTIVE` status
  - [x] Memory IDs stored in SSM

- [x] **Enable Memory Observability** (NOW we run the script we created)
  - [x] Run:
    ```bash
    python scripts/setup_memory_observability.py \
      --memory-id healthcare-basic-memory \
      --memory-id healthcare-premium-memory
    ```
  - [x] Verify CloudWatch log groups created
  - [x] Verify X-Ray traces enabled

- [ ] **Test Memory Functionality**
  - [ ] Run: `python test/test_memory.py load-conversation`
  - [ ] Run: `python test/test_memory.py load-prompt "Patient prefers morning appointments"`
  - [ ] Verify memory isolation per actor_id

**Deliverables**:
- 2 Memory resources with namespace templates
- Memory observability enabled
- Memory functionality tested

---

### 3.5 Agent Configuration & Cognito Users (Day 4)

**Follows**: `deploy.sh` lines 63-77 + user setup

- [x] **Configure Agents using direct code deployment**
  - [x] Get runtime role: `RUNTIME_ROLE=$(./scripts/list_ssm_parameters.sh | grep runtime_iam_role | cut -d'=' -f2)`
  - [x] Configure basic agent:
    ```bash
    agentcore configure --entrypoint main.py \
      -er "$RUNTIME_ROLE" \
      --name healthcare-basic
    ```
  - [x] Configure premium agent:
    ```bash
    agentcore configure --entrypoint main_premium.py \
      -er "$RUNTIME_ROLE" \
      --name healthcare-premium
    ```
  - [x] Deploy basic agent:
    ```bash
    agentcore deploy --agent healthcare_basic
    ```
  - [x] Deploy premium agent:
    ```bash
    agentcore deploy --agent healthcare_premium
    ```
  - [x] Clean up: `rm -f .agentcore.yaml`

- [x] **Create Test Users Script**
  - [x] Create `scripts/create_test_users.py`
  - [x] Script to create Cognito users with custom attributes
  - [x] Support for 8 clinic users (4 basic, 4 premium)
  - [x] Set custom:clinic_id and custom:tenant_id attributes
  - [x] Generate credentials document
  - [x] Make script idempotent (check if users exist before creating)
  - [x] Add error handling for existing users

- [x] **Add Custom Attributes to Cognito**
  - [x] Add `custom:clinic_id` attribute to user pool
  - [x] Add `custom:role` attribute
  - [x] Update user pool schema

- [x] **Integrate User Creation into deploy.sh**
  - [x] Add user creation step after agent configuration
  - [x] Add step in deploy.sh after line 127 (after premium agent configuration):
    ```bash
    print_step "Creating test users with clinic assignments..."
    python scripts/create_test_users.py
    ```
  - [x] Ensure script runs automatically during deployment
  - [x] Add success message showing created users
  - [x] Update final deployment message to include user credentials location

- [x] **Create Test Users** (Automated via deploy.sh)
  - [x] Script runs automatically during deployment
  - [x] Creates 8 users (4 basic, 4 premium)
  - [x] Sets custom:clinic_id and custom:tenant_id
  - [x] Generates credentials document at `credentials/test_users.json`

**Deliverables**:
- 2 AgentCore agents configured ✅
- Test user creation script created ✅
- Cognito user pool with custom attributes ✅
- 8 test users created automatically via deploy.sh ✅
- User credentials saved to credentials/test_users.json ✅

---

### 2.6 Test Baggage Propagation (Day 5)

**Critical**: Verify healthcare context is working

- [ ] **Deploy and Launch Agents**
  - [ ] Agents are automatically deployed via `agentcore deploy` in deploy.sh
  - [ ] Verify both agents deployed successfully
  - [ ] Check agent status: `agentcore status --agent healthcare_basic`
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

- [x] **Update Authentication** (`app_modules/auth.py`)
  - [x] Extend `get_enhanced_user_claims()` to extract clinic info
  - [x] Display clinic information in sidebar
  - [x] Add tier-specific badges
  - [x] Update SSM parameter paths to `/app/healthcare/*`

- [x] **Create Clinic-Aware Components** (`app_modules/ui_components.py`)
  - [x] `render_clinic_header()` - Display clinic branding
  - [x] `render_document_chat_interface()` - Document-focused chat
  - [x] `render_clinical_results()` - Structured result display
  - [x] `render_tier_features_sidebar()` - Tier-specific features display
  - [x] `render_prompt_suggestions()` - Tier-specific prompt suggestions
  - [x] `render_document_scope_indicator()` - Data isolation indicator
  - [x] `render_sidebar_user_info()` - User info and controls

- [x] **Update Main App** (`app_modules/main.py`)
  - [x] Replace customer support chat with clinical document chat
  - [x] Add document scope indicator
  - [x] Implement tier-specific prompt suggestions
  - [x] Update page title and icon for healthcare
  - [x] Integrate all new UI components
  - [x] Remove default conversation initialization (show suggestions instead)

**Deliverables**:
- Healthcare-focused Streamlit UI ✅
- Clinic-aware authentication and branding ✅
- Tier-specific features and prompt suggestions ✅
- Document scope indicators for data isolation ✅

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



