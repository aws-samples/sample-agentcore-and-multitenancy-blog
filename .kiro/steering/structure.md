# Project Structure

```
├── main.py                        # Unified AgentCore entrypoint (tier via AGENT_TIER env var)
├── app.py                         # Streamlit web UI entrypoint
│
├── agent/                         # Consolidated agent code (serves both tiers)
│   ├── agent.py                   # HealthcareAgent class — tier-configurable via TIER_CONFIG
│   ├── agent_task.py              # Async task runner for agent invocations
│   ├── context.py                 # TenantContext — ContextVar-based tenant state
│   ├── access_token.py            # Gateway bearer token acquisition
│   ├── memory_hook.py             # Strands MemoryHook for AgentCore Memory
│   ├── streaming_queue.py         # Async queue for streaming responses
│   ├── utils.py                   # SSM parameter helpers
│   └── tools/
│       └── retrieve_clinic_documents.py  # Knowledge Base retrieval with clinic filtering
│
├── app_modules/                   # Streamlit UI modules
│   ├── main.py                    # App entry, routing, authenticated interface
│   ├── auth.py                    # AuthManager — Cognito OAuth2 PKCE flow
│   ├── chat.py                    # ChatManager — invokes agent via API Gateway
│   ├── styles.py                  # Custom CSS
│   ├── ui_components.py           # Reusable Streamlit components
│   └── utils.py                   # UI utilities
│
├── scripts/                       # Deployment & management scripts
│   ├── prereq.sh                  # Infrastructure provisioning (CloudFormation)
│   ├── cleanup.sh                 # Full resource teardown
│   ├── agentcore_memory.py        # Create/manage AgentCore Memory resources
│   ├── agentcore_gateway.py       # Create/manage AgentCore Gateways
│   ├── agentcore_policy.py        # Policy engine (business hours enforcement)
│   ├── agentcore_agent_runtime.py # Runtime management
│   ├── configure_deployment.py    # Write SSM params from infra outputs
│   ├── create_inference_profiles.py  # Bedrock inference profiles for cost tracking
│   ├── create_test_users.py       # Cognito test user provisioning
│   ├── populate_healthcare_data.py   # Seed patient/clinic metadata in Lambda
│   ├── generate_healthcare_documents.py  # Synthetic clinical document generation
│   └── utils.py                   # Shared SSM/boto3 helpers
│
├── prerequisite/                  # Infrastructure-as-code
│   ├── infrastructure.yaml        # Core CloudFormation (IAM, S3, SSM)
│   ├── cognito_multitenant.yaml   # Cognito user pool with custom attributes
│   ├── api_gateway_template.yaml  # API Gateway + Lambda proxy
│   ├── knowledge_base.py          # KB creation script
│   ├── basic-documents/           # Sample clinical docs for basic tier
│   ├── premium-documents/         # Sample clinical docs for premium tier
│   └── lambda/                    # Lambda function code (healthcare only)
│
├── test/                          # Test suite
│   ├── test_agent.py
│   ├── test_gateway.py
│   ├── test_healthcare_tools.py
│   └── test_memory.py
│
├── config/                        # Deployment configuration
│   ├── deployment_config.json
│   └── parameters.template.yaml
│
├── credentials/                   # Test user credentials (gitignored)
├── deploy.sh                      # One-command full deployment
├── Dockerfile                     # Container deployment option
├── requirements.txt               # Production dependencies
└── dev-requirements.txt           # Dev/test dependencies
```

## Key Patterns

- **Single agent, tier-configurable**: `agent/agent.py` contains one `HealthcareAgent` class. Tier differences (model, tools, gateway target) are driven by `TIER_CONFIG` dict, not separate codepaths. Deploy two instances with `AGENT_TIER=basic` and `AGENT_TIER=premium`.
- **Context management**: `TenantContext` uses Python `ContextVar` for async-safe tenant state. Both global class vars and context vars are set for cross-call persistence.
- **Tool registration**: Tools use the Strands `@tool` decorator. Gateway tools are registered as static wrappers (not via `list_tools_sync()`) to work with the policy engine in ENFORCE mode.
- **SSM as config store**: All runtime configuration (KB IDs, memory IDs, gateway URLs, Cognito settings) is stored in SSM under `/app/healthcare/` and read at startup.
