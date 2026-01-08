# Multi-Tenant AgentCore Deployment Guide

This guide provides step-by-step instructions to deploy the multi-tenant customer support system built on Amazon Bedrock AgentCore.

## Prerequisites

### AWS Requirements
- AWS CLI configured with appropriate permissions
- AWS account with Bedrock access enabled
- AgentCore service enabled in your target region (us-east-1 recommended)
- IAM permissions for:
  - Bedrock model access (Claude 3.7 Sonnet)
  - Lambda function creation and execution
  - Cognito user pool management
  - SSM Parameter Store access
  - S3 bucket access for knowledge bases

### Local Requirements
- Python 3.8+
- Docker or Finch (for containerization)
- Git

## Quick Start (One-Command Deployment)

```bash
git clone <repository-url>
cd agentcore-multitenancy
chmod +x deploy.sh
./deploy.sh
```

## Manual Step-by-Step Deployment

### 1. Environment Setup

```bash
# Clone repository
git clone <repository-url>
cd agentcore-multitenancy

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r dev-requirements.txt
```

### 2. AWS Infrastructure Setup

```bash
# Create AWS resources (Cognito, Lambda, Knowledge Bases, etc.)
chmod +x scripts/prereq.sh
./scripts/prereq.sh

# Verify infrastructure creation
chmod +x scripts/list_ssm_parameters.sh
./scripts/list_ssm_parameters.sh
```

**⚠️ Important:** Ensure all resource names are prefixed with `customersupport`

### 3. AgentCore Gateway Setup

```bash
# Create shared gateway for both tenants
python scripts/agentcore_gateway.py create --name customersupport-gw
```

### 4. Identity and Authentication Setup

```bash
# Setup Cognito for authentication
python scripts/cognito_credentials_provider.py create --name customersupport-gateways

# Test gateway functionality
python test/test_gateway.py --prompt "Check warranty with serial number MNO33333333"
```

### 5. Memory Configuration (Multi-Tenant)

```bash
# Create memory for basic tier (gaming console)
python scripts/agentcore_memory.py create --name customersupport-basic

# Create memory for premium tier (financial services)
python scripts/agentcore_memory.py create --name customersupport-premium

# Test memory functionality
python test/test_memory.py load-conversation
python test/test_memory.py load-prompt "My preference of gaming console is V5 Pro"
python test/test_memory.py list-memory
```

### 6. Agent Runtime Configuration

```bash
# Get runtime IAM role from SSM
RUNTIME_ROLE=$(./scripts/list_ssm_parameters.sh | grep runtime_iam_role | cut -d'=' -f2)

# Configure basic tier agent (gaming console support)
agentcore configure --entrypoint main.py \
  -er $RUNTIME_ROLE \
  --name customersupport-basic

# Configure premium tier agent (financial services)
agentcore configure --entrypoint main_premium.py \
  -er $RUNTIME_ROLE \
  --name customersupport-premium
```

### 7. Launch and Test

```bash
# Remove any existing config
rm -f .agentcore.yaml

# Launch AgentCore runtime
agentcore launch

# In a separate terminal, start the web interface
streamlit run app.py --server.port 8501 -- --agent=customersupport-basic
```

## Testing the Deployment

```bash
# Run comprehensive deployment tests
chmod +x test_deployment.sh
./test_deployment.sh
```

## Multi-Tenant Architecture

### Basic Tier (Gaming Console Support)
- **Entrypoint:** `main.py`
- **Tools:** Customer profile, warranty checking
- **Knowledge Base:** Gaming console policies and manuals
- **Model:** Claude 3.7 Sonnet (basic inference profile)

### Premium Tier (Financial Services)
- **Entrypoint:** `main_premium.py`
- **Tools:** Client profile, portfolio summary
- **Knowledge Base:** Financial policies and guidelines
- **Model:** Claude 3.7 Sonnet (premium inference profile)

## Configuration Parameters

All configuration is stored in AWS SSM Parameter Store. Use the following command to view:

```bash
./scripts/list_ssm_parameters.sh
```

Key parameters include:
- `/app/customersupport/knowledge_base/knowledge_base_id` - Basic tier knowledge base
- `/app/customersupport/premium_knowledge_base/knowledge_base_id` - Premium tier knowledge base
- `/app/customersupport/agentcore/gateway_url` - MCP gateway endpoint
- `/app/customersupport/agentcore/runtime_iam_role` - AgentCore execution role

## Troubleshooting

### Common Issues

1. **Permission Errors**
   - Ensure AWS CLI is configured with sufficient permissions
   - Verify Bedrock model access is enabled

2. **Resource Creation Failures**
   - Check that resource names are prefixed with `customersupport`
   - Verify region availability for AgentCore

3. **Agent Configuration Issues**
   - Ensure runtime IAM role exists in SSM parameters
   - Verify entrypoint files (`main.py`, `main_premium.py`) exist

4. **Memory/Gateway Connection Issues**
   - Check SSM parameters are populated correctly
   - Verify network connectivity to AgentCore services

### Cleanup

To remove all resources:

```bash
chmod +x scripts/cleanup.sh
./scripts/cleanup.sh
```

## Next Steps

After successful deployment:

1. **Test Basic Tier:** Ask about gaming console warranty or troubleshooting
2. **Test Premium Tier:** Query financial portfolio or client information
3. **Customize:** Modify knowledge bases with your own content
4. **Scale:** Add additional tenants following the same pattern

## Support

For issues and questions:
- Check the troubleshooting section above
- Review AWS CloudWatch logs for detailed error information
- Ensure all prerequisites are met