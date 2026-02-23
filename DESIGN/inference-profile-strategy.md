# Inference Profile Strategy for Healthcare Multi-Tenancy

## Current Setup Analysis

### How It Currently Works

The existing system uses a **tier-based inference profile strategy** with 2 profiles:

1. **Basic Tier Profile**: `customersupport-basic-profile`
   - Model: Claude 3.7 Sonnet (`us.anthropic.claude-3-7-sonnet-20250219-v1:0`)
   - Tags: `Project=CustomerSupport`, `Tier=Basic`
   - Used by: Gaming console support agent

2. **Premium Tier Profile**: `customersupport-premium-profile`
   - Model: Claude 3.7 Sonnet (same model, different profile for cost tracking)
   - Tags: `Project=CustomerSupport`, `Tier=Premium`
   - Used by: Financial services agent

### Current Architecture Flow

```
deploy.sh
    ↓
scripts/create_inference_profiles.py
    ↓ Creates 2 profiles
    ↓ Stores ARNs in SSM
    ↓
scripts/configure_deployment.py
    ↓ Reads SSM parameters
    ↓ Updates agent_config/agent.py with ARNs (regex replacement)
    ↓
agent_config/agent.py
    ↓ Maps tenant_id → inference profile ARN
    ↓ "basic" → basic profile ARN
    ↓ "premium" → premium profile ARN
```

### Key Implementation Details

**1. Profile Creation** (`scripts/create_inference_profiles.py`):
```python
# Creates profiles with tags for cost tracking
bedrock_client.create_application_inference_profile(
    inferenceProfileName="customersupport-basic-profile",
    modelSource={'copyFrom': model_id},
    tags=[
        {'key': 'Project', 'value': 'CustomerSupport'},
        {'key': 'Tier', 'value': 'Basic'}
    ]
)
```

**2. SSM Storage**:
- `/app/customersupport/inference_profiles/basic_arn`
- `/app/customersupport/inference_profiles/premium_arn`

**3. Agent Mapping** (`agent_config/agent.py`):
```python
inference_profile_mapping = {
    "basic": "arn:aws:bedrock:us-east-1:ACCOUNT:application-inference-profile/ID",
    "premium": "arn:aws:bedrock:us-east-1:ACCOUNT:application-inference-profile/ID",
    "default": "arn:aws:bedrock:us-east-1:ACCOUNT:application-inference-profile/ID"
}
self.model_id = inference_profile_mapping.get(tenant_id, bedrock_model_id)
```

---

## Healthcare Transformation Strategy

### Option 1: Tier-Level Profiles (RECOMMENDED - Minimal Changes)

**Approach**: Keep 2 profiles but change models and tags for healthcare

**Advantages**:
- ✅ Minimal code changes (only model IDs and tags)
- ✅ Works with existing deployment flow
- ✅ Simple cost tracking (2 profiles = 2 cost buckets)
- ✅ Fast implementation (1-2 days)

**Implementation**:

```python
# scripts/create_inference_profiles.py - MODIFIED

def main():
    """Create healthcare-specific inference profiles"""
    
    # Basic tier: Nova Micro (cost-effective)
    basic_profile_arn = create_inference_profile(
        bedrock_client,
        "healthcare-basic-profile",
        model_id="us.amazon.nova-micro-v1:0"  # CHANGED
    )
    
    # Premium tier: Nova 2 Lite (with built-in web grounding)
    premium_profile_arn = create_inference_profile(
        bedrock_client,
        "healthcare-premium-profile",
        model_id="us.amazon.nova-2-lite-v1:0"  # CHANGED - Nova 2 Lite
    )
    
    # Store in SSM with healthcare prefix
    store_profile_arn_in_ssm(
        ssm_client,
        "/app/healthcare/inference_profiles/basic_arn",  # CHANGED
        basic_profile_arn
    )
    store_profile_arn_in_ssm(
        ssm_client,
        "/app/healthcare/inference_profiles/premium_arn",  # CHANGED
        premium_profile_arn
    )
```

**Cost Tracking**:
- All basic tier clinics (A, B, C, D) share basic profile → aggregated costs
- All premium tier clinics (Hospital A, Clinic E, F, Hospital B) share premium profile → aggregated costs
- Use OpenTelemetry baggage for per-clinic breakdown within each tier

**Agent Mapping** (no changes needed):
```python
# agent_config/agent.py - NO CHANGES NEEDED
inference_profile_mapping = {
    "basic": "arn:aws:bedrock:us-east-1:ACCOUNT:application-inference-profile/BASIC_ID",
    "premium": "arn:aws:bedrock:us-east-1:ACCOUNT:application-inference-profile/PREMIUM_ID",
    "default": "arn:aws:bedrock:us-east-1:ACCOUNT:application-inference-profile/BASIC_ID"
}
```

### Implementation Checklist

#### Phase 1: Inference Profile Updates (Day 1 - Morning)

- [ ] **Step 1**: Update `scripts/create_inference_profiles.py`
  - Change profile names: `healthcare-basic-profile`, `healthcare-premium-profile`
  - Change model IDs:
    - Basic: `us.amazon.nova-micro-v1:0`
    - Premium: `us.amazon.nova-2-lite-v1:0` (Nova 2 Lite with web grounding)
  - Update tags for cost tracking:
    ```python
    tags=[
        {'key': 'Project', 'value': 'HealthcareDemo'},
        {'key': 'Tier', 'value': 'Basic'},  # or 'Premium'
        {'key': 'Environment', 'value': 'demo'}
    ]
    ```
  - Update SSM paths: `/app/healthcare/inference_profiles/basic_arn` and `premium_arn`

- [ ] **Step 2**: Update `scripts/configure_deployment.py`
  - Change SSM parameter paths to `/app/healthcare/*`
  - Update regex patterns to match new profile names
  - Keep existing 2-profile mapping structure

- [ ] **Step 3**: Update `agent_config/agent.py` and `agent_config_premium/agent.py`
  - Keep existing `inference_profile_mapping` structure (no changes)
  - ARNs will be auto-updated by `configure_deployment.py`
  - Verify model selection logic remains unchanged

#### Phase 2: Cost Tracking Setup (Day 1 - Afternoon)

- [ ] **Step 4**: Enable Memory Observability (CRITICAL for cost tracking)
  - **Option A**: Run script `scripts/setup_memory_observability.py`
    ```bash
    python scripts/setup_memory_observability.py \
      --memory-id healthcare-basic-memory \
      --memory-id healthcare-premium-memory
    ```
  - **Option B**: Enable via AWS Console
    - Navigate to: AgentCore Console → Memory Resources
    - Select `healthcare-basic-memory` → Configure observability
    - Enable "Application logs" → CloudWatch Logs
    - Enable "Traces" → AWS X-Ray
    - Repeat for `healthcare-premium-memory`
  - Verify log groups created:
    - `/aws/vendedlogs/bedrock-agentcore/memory/APPLICATION_LOGS/healthcare-basic-memory`
    - `/aws/vendedlogs/bedrock-agentcore/memory/APPLICATION_LOGS/healthcare-premium-memory`

- [ ] **Step 5**: Add OpenTelemetry baggage in `main.py` and `main_premium.py`
  - Import: `from opentelemetry import baggage, context`
  - Add at entrypoint (after extracting tenant info):
    ```python
    # Set baggage for cost attribution (3 lines)
    ctx = baggage.set_baggage("tenant_id", tenant_info['tenant_key'])
    ctx = baggage.set_baggage("tier", tenant_info['tier'])
    ctx = baggage.set_baggage("clinic_id", tenant_info['clinic_id'])
    ctx = baggage.set_baggage("actor_id", tenant_info['actor_id'])
    context.attach(ctx)
    ```
  - Verify baggage propagates to all operations

- [ ] **Step 6**: Enable Cost Allocation Tags in AWS Billing Console
  - Navigate to: AWS Billing Console → Cost Allocation Tags
  - Activate tags: `Project`, `Tier`, `Environment`
  - **Note**: Takes 24 hours to appear in Cost Explorer
  - Document activation timestamp

#### Phase 3: Deployment & Testing (Day 2)

- [ ] **Step 7**: Update `deploy.sh`
  - Change all `customersupport` references to `healthcare`
  - Update agent names: `healthcare-basic`, `healthcare-premium`
  - Update SSM parameter paths
  - Keep existing deployment flow

- [ ] **Step 8**: Deploy and verify
  ```bash
  ./deploy.sh
  ```
  - Verify profiles created with correct models
  - Verify SSM parameters updated
  - Verify agents deployed successfully
  - Test with sample requests

- [ ] **Step 9**: Verify cost tracking working
  - Send test requests with different clinic_ids
  - Check CloudWatch Logs for baggage fields:
    - `baggage.tenant_id`
    - `baggage.tier`
    - `baggage.clinic_id`
  - Verify GenAI Observability dashboard shows runtime metrics
  - Verify Memory logs show tenant_id (after observability enabled)

#### Phase 4: Cost Reporting (Day 3)

- [ ] **Step 10**: Create CloudWatch Logs Insights saved queries
  - Runtime costs per clinic
  - Memory costs per clinic
  - Combined cost summary
  - Save queries for easy access

- [ ] **Step 11**: Create cost reporting script `scripts/generate_cost_report.py`
  - Query Cost Explorer for model costs (by Tier tag)
  - Query CloudWatch Logs for runtime costs (by baggage.clinic_id)
  - Query CloudWatch Logs for memory costs (by tenant_id)
  - Generate CSV report with per-clinic breakdown
  - Calculate tier comparison (Basic vs Premium)

- [ ] **Step 12**: Generate sample cost report for demo
  - Run cost report script for test period
  - Document cost differences (Basic vs Premium)
  - Create visualization (optional: QuickSight dashboard)
  - Prepare demo talking points

### Expected Costs (Demo Scenario)

#### Model Costs (Dominant - 95%+ of total)

**Basic Tier (Nova Micro)**:
- Input: $0.000035 per 1K tokens
- Output: $0.00014 per 1K tokens
- Example: 100K input + 50K output = $0.0035 + $0.007 = **$0.0105 per clinic**

**Premium Tier (Nova 2 Lite)**:
- Input: $0.00035 per 1K tokens
- Output: $0.0014 per 1K tokens
- Example: 100K input + 50K output = $0.035 + $0.07 = **$0.105 per clinic**
- **Built-in web grounding** - no external API costs!

**Cost Difference**: 10x (demonstrates clear tier differentiation while keeping costs reasonable!)

#### Runtime Costs (Minimal - <5% of total)

**AgentCore Runtime** (tracked via observability baggage):
- CPU: $0.000011 per vCPU-second
- Memory: $0.0000012 per GB-second
- Example: 1 hour runtime (3600s) with 512MB = **$0.042 per clinic**

#### Memory Costs (Minimal - <5% of total)

**AgentCore Memory** (tracked via observability baggage after enablement):
- Events: $0.000001 per event
- Retrievals: $0.000004 per retrieval
- Storage: $0.10 per GB-month
- Example: 10K events + 5K retrievals = **$0.03 per clinic**

#### Total Cost Example (Monthly)

**Clinic A (Basic Tier)**:
- Model: $0.24 (1M input + 500K output tokens)
- Runtime: $0.04 (3600 CPU-seconds)
- Memory: $0.03 (10K events + 5K retrievals)
- **Total: $0.31/month**

**Hospital A (Premium Tier)**:
- Model: $1.05 (1M input + 500K output tokens with Nova 2 Lite)
- Runtime: $0.06 (5400 CPU-seconds)
- Memory: $0.05 (15K events + 8K retrievals)
- **Total: $1.16/month**

**Key Insight**: Premium costs **3.7x more** due to Nova 2 Lite pricing + web grounding capability, demonstrating clear tier value differentiation while keeping costs reasonable!

---

## Migration Path from Current System

### Phase 1: Profile Recreation (Day 1)
1. Delete old profiles: `customersupport-basic-profile`, `customersupport-premium-profile`
2. Run updated `scripts/create_inference_profiles.py`
3. Verify new profiles created with healthcare names and models
4. Verify SSM parameters updated

### Phase 2: Configuration Update (Day 1)
1. Run `scripts/configure_deployment.py`
2. Verify agent files updated with new profile ARNs
3. Test agent initialization locally

### Phase 3: Baggage Integration (Day 2)
1. Add OpenTelemetry baggage to `main.py` and `main_premium.py`
2. Test baggage propagation in CloudWatch Logs
3. Verify clinic_id appears in logs

### Phase 4: Deployment (Day 2)
1. Update `deploy.sh` with healthcare names
2. Run full deployment
3. Test with sample clinics
4. Verify cost tracking working

### Phase 5: Cost Reporting (Day 3)
1. Create `scripts/generate_cost_report.py`
2. Test cost queries against CloudWatch Logs
3. Generate sample cost reports
4. Document cost attribution methodology

---

## Testing Strategy

### Unit Tests
```python
# test/test_inference_profiles.py

def test_basic_tier_uses_nova_micro():
    """Verify basic tier uses Nova Micro model"""
    agent = CustomerSupport(tenant_id="basic", clinic_id="clinic-a")
    assert "nova-micro" in agent.model_id.lower()

def test_premium_tier_uses_nova_2():
    """Verify premium tier uses Nova 2 Lite model"""
    agent = CustomerSupport(tenant_id="premium", clinic_id="hospital-a")
    assert "nova-2-lite" in agent.model_id.lower()

def test_clinic_isolation():
    """Verify different clinics use same tier profile"""
    agent_a = CustomerSupport(tenant_id="basic", clinic_id="clinic-a")
    agent_b = CustomerSupport(tenant_id="basic", clinic_id="clinic-b")
    assert agent_a.model_id == agent_b.model_id  # Same profile
```

### Integration Tests
```python
# test/test_cost_tracking.py

def test_baggage_propagation():
    """Verify OpenTelemetry baggage includes clinic_id"""
    # Invoke agent
    response = invoke_agent(clinic_id="clinic-a", query="Test")
    
    # Check CloudWatch Logs
    logs = query_cloudwatch_logs()
    assert "baggage.clinic_id" in logs
    assert logs["baggage.clinic_id"] == "clinic-a"

def test_cost_attribution():
    """Verify costs can be attributed to specific clinics"""
    # Generate test traffic for multiple clinics
    invoke_agent(clinic_id="clinic-a", query="Test 1")
    invoke_agent(clinic_id="clinic-b", query="Test 2")
    
    # Query costs
    costs = get_clinic_costs()
    assert "clinic-a" in costs
    assert "clinic-b" in costs
    assert costs["clinic-a"] != costs["clinic-b"]
```

---

## Troubleshooting Guide

### Issue: Profile ARNs not updating in agent files
**Solution**: Run `scripts/configure_deployment.py` manually after profile creation

### Issue: Agent using wrong model
**Solution**: Check SSM parameters, verify profile ARN mapping in agent.py

### Issue: Baggage not appearing in CloudWatch Logs
**Solution**: Verify observability enabled in `.bedrock_agentcore.yaml`, check baggage.set_baggage() calls

### Issue: Cost tracking not working
**Solution**: Enable cost allocation tags in AWS Billing Console (24-hour delay), verify baggage propagation

---

## Summary

**Current System**: 2 tier-level profiles with same model (Claude 3.7 Sonnet)

**Healthcare System**: 2 tier-level profiles with different Nova models (Nova Micro vs Nova 2 Lite)

**Key Changes**:
1. Model IDs (Nova Micro for basic, Nova 2 Lite for premium)
2. Profile names (healthcare-* instead of customersupport-*)
3. SSM paths (/app/healthcare/* instead of /app/customersupport/*)
4. OpenTelemetry baggage (add clinic_id for cost tracking)
5. Tags (HealthcareDemo project, clinic metadata)
6. **Premium web grounding** (enabled via Nova 2 `tool_config` - no Lambda needed!)

**Implementation Time**: 2-3 days

**Complexity**: Low (reuses existing architecture)

**Demo Value**: High (clear tier differentiation, native web search, accurate cost tracking)
