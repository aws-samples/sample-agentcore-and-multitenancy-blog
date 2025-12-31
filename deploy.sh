#!/bin/bash

# Multi-Tenant AgentCore Deployment Script
# Based on the reference pattern but adapted for multi-tenancy

set -e

echo "🚀 Starting Multi-Tenant AgentCore Deployment"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_step() {
    echo -e "${GREEN}[STEP]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    print_step "Creating Python virtual environment..."
    python -m venv .venv
fi

print_step "Activating virtual environment and installing dependencies..."
source .venv/bin/activate
pip install -r dev-requirements.txt

print_step "Creating AWS infrastructure..."
chmod +x scripts/prereq.sh
./scripts/prereq.sh

print_step "Creating Bedrock inference profiles..."
python scripts/create_inference_profiles.py

print_step "Updating configuration with created resources..."
python scripts/configure_deployment.py

print_step "Listing SSM parameters..."
chmod +x scripts/list_ssm_parameters.sh
./scripts/list_ssm_parameters.sh

print_warning "Please ensure all resource names are prefixed with 'healthcare'"

print_step "Creating AgentCore Gateways (Basic and Premium)..."
python scripts/agentcore_gateway.py create-all

print_step "Setting up Cognito Credential Provider..."
python scripts/cognito_credentials_provider.py create --name healthcare-cognito-provider

print_step "Creating Memory Resources (Basic and Premium)..."
python scripts/agentcore_memory.py create-all

print_step "Testing gateway with basic tenant..."
python test/test_gateway.py --prompt "Check warranty with serial number MNO33333333"

print_step "Testing memory functionality..."
python test/test_memory.py load-conversation
python test/test_memory.py load-prompt "My preference of gaming console is V5 Pro"
python test/test_memory.py list-memory

print_step "Getting runtime role from SSM..."
RUNTIME_ROLE=$(./scripts/list_ssm_parameters.sh | grep runtime_iam_role | cut -d'=' -f2 | tr -d ' ')

if [ -z "$RUNTIME_ROLE" ]; then
    print_error "Could not retrieve runtime IAM role from SSM parameters"
    exit 1
fi

print_step "Configuring basic tier agent..."
agentcore configure --entrypoint main.py \
  -er "$RUNTIME_ROLE" \
  --name healthcare-basic

print_step "Configuring premium tier agent..."
agentcore configure --entrypoint main_premium.py \
  -er "$RUNTIME_ROLE" \
  --name healthcare-premium

print_step "Removing old agentcore config..."
rm -f .agentcore.yaml

print_step "Deployment completed successfully!"
echo ""
echo "🎉 Multi-tenant AgentCore deployment is ready!"
echo ""
echo "To launch the agents:"
echo "1. Launch AgentCore: agentcore launch"
echo "2. In another terminal, start Streamlit: streamlit run app.py --server.port 8501 -- --agent=healthcare-basic"
echo ""
echo "Available agents:"
echo "- healthcare-basic"
echo "- healthcare-premium"
echo ""
echo "Use ./scripts/list_ssm_parameters.sh to view configuration parameters"