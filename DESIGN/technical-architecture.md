## Technical Architecture

This documents contains document storage structure, tenant identification, agent config, chat interface, and API gateway configuration. For memory and cost tracking, you can find more information under the /DESIGN forder.

### S3 Document Storage Structure

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