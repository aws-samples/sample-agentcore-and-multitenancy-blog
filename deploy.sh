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

# --- Pre-flight checks ---

# Detect Python command (python3 preferred, fallback to python)
if command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
elif command -v python &>/dev/null; then
    PYTHON_CMD="python"
else
    print_error "Python is not installed. Please install Python 3.9+ and try again."
    exit 1
fi

PYTHON_VERSION=$($PYTHON_CMD -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
print_info "Using Python: $PYTHON_CMD (version $PYTHON_VERSION)"

# Verify AWS credentials are configured
if ! aws sts get-caller-identity &>/dev/null; then
    print_error "AWS credentials are not configured or have expired."
    print_info "Please set your AWS profile before running this script:"
    print_info "  export AWS_PROFILE=<your-profile-name>"
    print_info "Or configure credentials via: aws configure"
    exit 1
fi

AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query 'Account' --output text)
AWS_IDENTITY=$(aws sts get-caller-identity --query 'Arn' --output text)
print_info "AWS Account: $AWS_ACCOUNT_ID"
print_info "AWS Identity: $AWS_IDENTITY"
if [ -n "$AWS_PROFILE" ]; then
    print_info "AWS Profile: $AWS_PROFILE"
fi

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    print_step "Creating Python virtual environment..."
    $PYTHON_CMD -m venv .venv
fi

print_step "Activating virtual environment and installing dependencies..."
source .venv/bin/activate
pip install -r requirements.txt

print_step "Creating AWS infrastructure..."
chmod +x scripts/prereq.sh
./scripts/prereq.sh

print_step "Populating healthcare data (patient metadata and clinic configurations)..."
python scripts/populate_healthcare_data.py

print_step "Creating Bedrock projects for cost attribution..."
python scripts/create_bedrock_projects.py


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

print_step "Creating AgentCore Policy Engine (Business Hours Enforcement)..."
python scripts/agentcore_policy.py create

print_step "Creating Bedrock Guardrails (Basic and Premium)..."
python scripts/bedrock_guardrails.py create

print_step "Setting up Cognito Credential Provider..."
python scripts/cognito_credentials_provider.py create --name healthcare-cognito-provider

print_step "Creating Memory Resources (Basic and Premium)..."
python scripts/agentcore_memory.py create-all

print_step "Enabling Memory Observability for cost tracking..."
python scripts/setup_memory_observability.py enable-all

print_step "Verifying Memory Observability configuration..."
python scripts/setup_memory_observability.py verify-all || echo -e "${YELLOW}[WARNING]${NC} Memory observability verification incomplete — deliveries may take time to propagate. This is non-blocking."

print_step "Getting runtime role from SSM..."
RUNTIME_ROLE=$(aws ssm get-parameter --name /app/healthcare/agentcore/runtime_iam_role --query 'Parameter.Value' --output text)

if [ -z "$RUNTIME_ROLE" ]; then
    print_error "Could not retrieve runtime IAM role from SSM parameters"
    exit 1
fi

print_info "Runtime IAM Role: $RUNTIME_ROLE"

print_step "Getting Cognito configuration for JWT authorization..."
COGNITO_DISCOVERY_URL=$(aws ssm get-parameter --name /app/healthcare/agentcore/cognito_discovery_url --query 'Parameter.Value' --output text)
COGNITO_MACHINE_CLIENT_ID=$(aws ssm get-parameter --name /app/healthcare/agentcore/machine_client_id --query 'Parameter.Value' --output text)
COGNITO_WEB_CLIENT_ID=$(aws ssm get-parameter --name /app/healthcare/agentcore/web_client_id --query 'Parameter.Value' --output text)

if [ -z "$COGNITO_DISCOVERY_URL" ] || [ -z "$COGNITO_MACHINE_CLIENT_ID" ] || [ -z "$COGNITO_WEB_CLIENT_ID" ]; then
    print_error "Could not retrieve Cognito configuration from SSM parameters"
    exit 1
fi

print_info "Cognito Discovery URL: $COGNITO_DISCOVERY_URL"
print_info "Cognito Machine Client ID: $COGNITO_MACHINE_CLIENT_ID"
print_info "Cognito Web Client ID: $COGNITO_WEB_CLIENT_ID"

# Build JWT authorizer configuration with both allowedClients (for access tokens) and allowedAudience (for ID tokens)
# AUTHORIZER_CONFIG="{\"customJWTAuthorizer\":{\"discoveryUrl\":\"$COGNITO_DISCOVERY_URL\",\"allowedClients\":[\"$COGNITO_MACHINE_CLIENT_ID\",\"$COGNITO_WEB_CLIENT_ID\"],\"allowedAudience\":[\"$COGNITO_WEB_CLIENT_ID\"]}}"
AUTHORIZER_CONFIG="{\"customJWTAuthorizer\":{\"discoveryUrl\":\"$COGNITO_DISCOVERY_URL\",\"allowedAudience\":[\"$COGNITO_WEB_CLIENT_ID\"]}}"

print_step "Configuring basic tier agent with JWT authorization..."
if [ "$DEPLOYMENT_TYPE" = "direct_code_deploy" ]; then
    agentcore configure --entrypoint main.py \
      -er "$RUNTIME_ROLE" \
      --name healthcare_basic \
      --deployment-type direct_code_deploy \
      --runtime "$PYTHON_RUNTIME" \
      --authorizer-config "$AUTHORIZER_CONFIG" \
      --request-header-allowlist "Authorization" \
      --non-interactive
else
    agentcore configure --entrypoint main.py \
      -er "$RUNTIME_ROLE" \
      --name healthcare_basic \
      --deployment-type container \
      --authorizer-config "$AUTHORIZER_CONFIG" \
      --request-header-allowlist "Authorization" \
      --non-interactive
fi

print_step "Configuring premium tier agent with JWT authorization..."
if [ "$DEPLOYMENT_TYPE" = "direct_code_deploy" ]; then
    agentcore configure --entrypoint main.py \
      -er "$RUNTIME_ROLE" \
      --name healthcare_premium \
      --deployment-type direct_code_deploy \
      --runtime "$PYTHON_RUNTIME" \
      --authorizer-config "$AUTHORIZER_CONFIG" \
      --request-header-allowlist "Authorization" \
      --non-interactive
else
    agentcore configure --entrypoint main.py \
      -er "$RUNTIME_ROLE" \
      --name healthcare_premium \
      --deployment-type container \
      --authorizer-config "$AUTHORIZER_CONFIG" \
      --request-header-allowlist "Authorization" \
      --non-interactive
fi

print_step "Creating test users with clinic assignments..."
python scripts/create_test_users.py

if [ $? -eq 0 ]; then
    print_info "Test users created successfully"
else
    print_warning "Some test users may have failed to create. Check output above."
fi

print_step "Deploying basic tier agent to AWS..."
agentcore deploy --agent healthcare_basic

print_step "Deploying premium tier agent to AWS..."
agentcore deploy --agent healthcare_premium

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
echo "Agents deployed and ready to use!"
echo ""
echo "To use the web interface:"
echo "  streamlit run app.py --server.port 8501"
echo ""
echo "📋 Test Users Created:"
echo "  Basic Tier (4 users):"
echo "    - dr.smith@clinic-a.com (Clinic A - Family Practice)"
echo "    - nurse.lee@clinic-a.com (Clinic A - Family Practice)"
echo "    - dr.chen@clinic-b.com (Clinic B - Urgent Care)"
echo "    - dr.rodriguez@clinic-c.com (Clinic C - Pediatrics)"
echo ""
echo "  Premium Tier (4 users):"
echo "    - dr.foster@hospital-a.com (Hospital A - Multi-Specialty)"
echo "    - dr.wilson@hospital-a.com (Hospital A - Multi-Specialty)"
echo "    - dr.anderson@clinic-e.com (Clinic E - Cardiology)"
echo "    - dr.green@clinic-f.com (Clinic F - Oncology)"
echo ""
echo "  Temporary Password: TempPass123!"
echo "  Full credentials:   credentials/test_users.json"
echo ""
echo "Use ./scripts/list_ssm_parameters.sh to view configuration parameters"