#!/bin/bash

# Multi-Tenant AgentCore Deployment Script
# Based on the reference pattern but adapted for multi-tenancy

set -e

echo "🚀 Starting Multi-Tenant AgentCore Deployment"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
DEPLOYMENT_TYPE="${DEPLOYMENT_TYPE:-direct_code_deploy}"  # Default to direct_code_deploy, set to "container" for container deployment
PYTHON_RUNTIME="${PYTHON_RUNTIME:-PYTHON_3_12}"  # For direct_code_deploy only

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

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
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

print_step "Populating healthcare data (patient metadata and clinic configurations)..."
python scripts/populate_healthcare_data.py

print_step "Creating Bedrock inference profiles..."
python scripts/create_inference_profiles.py

print_info "Deployment type: ${DEPLOYMENT_TYPE}"
if [ "$DEPLOYMENT_TYPE" = "direct_code_deploy" ]; then
    print_info "Python runtime: ${PYTHON_RUNTIME}"
fi

print_step "Updating configuration with created resources..."
python scripts/configure_deployment.py "$DEPLOYMENT_TYPE"

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

print_step "Enabling Memory Observability for cost tracking..."
python scripts/setup_memory_observability.py enable-all

print_step "Verifying Memory Observability configuration..."
python scripts/setup_memory_observability.py verify-all

print_step "Getting runtime role from SSM..."
RUNTIME_ROLE=$(./scripts/list_ssm_parameters.sh | grep runtime_iam_role | cut -d'=' -f2 | tr -d ' ')

if [ -z "$RUNTIME_ROLE" ]; then
    print_error "Could not retrieve runtime IAM role from SSM parameters"
    exit 1
fi

print_info "Runtime IAM Role: $RUNTIME_ROLE"

print_step "Configuring basic tier agent..."
if [ "$DEPLOYMENT_TYPE" = "direct_code_deploy" ]; then
    agentcore configure --entrypoint main.py \
      -er "$RUNTIME_ROLE" \
      --name healthcare_basic \
      --deployment-type direct_code_deploy \
      --runtime "$PYTHON_RUNTIME" \
      --non-interactive
else
    agentcore configure --entrypoint main.py \
      -er "$RUNTIME_ROLE" \
      --name healthcare_basic \
      --deployment-type container \
      --non-interactive
fi

print_step "Configuring premium tier agent..."
if [ "$DEPLOYMENT_TYPE" = "direct_code_deploy" ]; then
    agentcore configure --entrypoint main_premium.py \
      -er "$RUNTIME_ROLE" \
      --name healthcare_premium \
      --deployment-type direct_code_deploy \
      --runtime "$PYTHON_RUNTIME" \
      --non-interactive
else
    agentcore configure --entrypoint main_premium.py \
      -er "$RUNTIME_ROLE" \
      --name healthcare_premium \
      --deployment-type container \
      --non-interactive
fi


print_step "Deployment completed successfully!"
echo ""
echo "🎉 Multi-tenant AgentCore deployment is ready!"
echo ""
echo "Deployment Configuration:"
echo "  Type: $DEPLOYMENT_TYPE"
if [ "$DEPLOYMENT_TYPE" = "direct_code_deploy" ]; then
    echo "  Runtime: $PYTHON_RUNTIME"
fi
echo ""
echo "To deploy the agents:"
echo "  agentcore deploy --agent healthcare_basic"
echo "  agentcore deploy --agent healthcare_premium"
echo ""
echo "To launch the agents (after deployment):"
echo "1. Start Streamlit: streamlit run app.py --server.port 8501 -- --agent=healthcare-basic"
echo ""
echo "Available agents:"
echo "- healthcare_basic"
echo "- healthcare_premium"
echo ""
echo "Use ./scripts/list_ssm_parameters.sh to view configuration parameters"