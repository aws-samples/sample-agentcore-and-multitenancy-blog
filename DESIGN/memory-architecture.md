
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
- [x] Create 2 Memory resources (basic-tier, premium-tier) with namespace templates
- [x] Configure namespace templates: `"clinic/{actorId}/facts/{sessionId}"`
- [x] Store Memory resource IDs in SSM:
  - `/app/healthcare/memory/basic_id`
  - `/app/healthcare/memory/premium_id`
- [ ] Verify Memory resources are ACTIVE

**Phase 2: JWT and Actor ID Configuration**
- [x] Update JWT parsing to extract `user_id` from `cognito:username`
- [x] Implement hierarchical `actor_id` construction: `"{tier}-{clinic_id}-{user_id}"`
- [x] Update agent code to use user-specific `actor_id` for all memory operations
- [x] Add logging for `actor_id` generation for debugging

**Phase 3: Agent Integration**
- [x] Update `main.py` to initialize `MemorySessionManager` with tier-specific memory
- [x] Update `main_premium.py` similarly
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
4. **Memory observability setup** (one-time configuration per Memory resource)

**Result**: Complete cost visibility per clinic
- Model costs: Tagged inference profiles → Cost Explorer
- Runtime costs: Observability baggage → CloudWatch Logs (automatic)
- Memory costs: Observability baggage → CloudWatch Logs (after setup)
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