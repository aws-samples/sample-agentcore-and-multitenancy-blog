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
# The AgentCore Runtimes use direct code deployment: the artifact is a zip in
# S3 built by scripts/package_agent.sh. DEPLOYMENT_TYPE is retained because
# configure_deployment.py still reads it.
DEPLOYMENT_TYPE="${DEPLOYMENT_TYPE:-direct_code_deploy}"
PYTHON_RUNTIME="${PYTHON_RUNTIME:-PYTHON_3_12}"

# AgentCore Runtime platform version. V2 restores a prepared snapshot per
# session instead of initializing the environment, which keeps cold starts
# fast and consistent. Set to V1 to compare against the original behavior.
AGENTCORE_PLATFORM_VERSION="${AGENTCORE_PLATFORM_VERSION:-V2}"

# Must match the bucket and stack naming that scripts/prereq.sh uses.
BUCKET_NAME="${BUCKET_NAME:-healthcare}"
RUNTIME_STACK_NAME="${RUNTIME_STACK_NAME:-HealthcareStackRuntime}"

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
REGION=$(aws configure get region)
FULL_BUCKET_NAME="${BUCKET_NAME}-${AWS_ACCOUNT_ID}"
print_info "AWS Account: $AWS_ACCOUNT_ID"
print_info "AWS Region: $REGION"
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

print_step "Publishing MCP gateway records to Agent Registry..."
python scripts/registry_publisher.py

print_step "Configuring AgentCore Gateway rate limits (per-user and per-target)..."
python scripts/agentcore_rate_limits.py create

print_step "Creating AgentCore Policy Engine (Business Hours Enforcement)..."
python scripts/agentcore_policy.py create

print_step "Creating Bedrock Guardrails (Basic and Premium)..."
python scripts/bedrock_guardrails.py create

print_step "Setting up Cognito Credential Provider..."
python scripts/cognito_credentials_provider.py create --name healthcare-cognito-provider

print_step "Creating Memory Resources (Basic and Premium)..."
python scripts/agentcore_memory.py create-all

print_step "Enabling Memory Observability for cost tracking..."
python scripts/setup_memory_observability.py enable-all || print_warning "Memory observability setup had issues — this is non-blocking. You can retry with: python scripts/setup_memory_observability.py enable-all"

print_step "Verifying Memory Observability configuration..."
python scripts/setup_memory_observability.py verify-all || echo -e "${YELLOW}[WARNING]${NC} Memory observability verification incomplete — deliveries may take time to propagate. This is non-blocking."

print_step "Creating test users with clinic assignments..."
python scripts/create_test_users.py

if [ $? -eq 0 ]; then
    print_info "Test users created successfully"
else
    print_warning "Some test users may have failed to create. Check output above."
fi

# ----------------------------------------------------------------------------
# AgentCore Runtimes (infrastructure as code)
#
# The runtimes are declared in prerequisite/agentcore_runtime.yaml rather than
# created with 'agentcore configure' + 'agentcore deploy'. Two reasons:
#
#   1. The bedrock-agentcore-starter-toolkit is no longer supported, and its
#      successor (@aws/agentcore) is a different toolchain entirely.
#   2. Neither CLI can set platformVersion, so neither can create a V2 runtime.
#      AWS::BedrockAgentCore::Runtime exposes PlatformVersion directly.
#
# The template reads the execution role and Cognito settings straight from SSM,
# which is why the shell no longer fetches them and passes them along.
# ----------------------------------------------------------------------------

print_step "Packaging agent bundle for AgentCore Runtime..."
CODE_PREFIX=$(scripts/package_agent.sh "$FULL_BUCKET_NAME")

if [ -z "$CODE_PREFIX" ]; then
    print_error "Agent packaging failed; no bundle key returned"
    exit 1
fi

print_info "Agent bundle: s3://$FULL_BUCKET_NAME/$CODE_PREFIX"

print_step "Deploying AgentCore Runtimes (platform version ${AGENTCORE_PLATFORM_VERSION})..."
print_info "A V2 runtime prepares and snapshots its environment, so this takes"
print_info "several minutes per runtime rather than seconds."

aws cloudformation deploy \
  --stack-name "$RUNTIME_STACK_NAME" \
  --template-file prerequisite/agentcore_runtime.yaml \
  --region "$REGION" \
  --parameter-overrides \
    CodeBucket="$FULL_BUCKET_NAME" \
    CodePrefix="$CODE_PREFIX" \
    PlatformVersion="$AGENTCORE_PLATFORM_VERSION" \
    PythonRuntime="$PYTHON_RUNTIME"

print_step "Verifying runtime platform version..."
for tier in basic premium; do
    runtime_id=$(aws ssm get-parameter \
      --name "/app/healthcare/agentcore/${tier}_agent_id" \
      --query 'Parameter.Value' --output text 2>/dev/null)

    if [ -n "$runtime_id" ]; then
        # Read back through Cloud Control, which uses the resource schema and
        # therefore reports PlatformVersion even on AWS CLI versions whose
        # bedrock-agentcore-control model predates the field.
        details=$(aws cloudcontrol get-resource \
          --type-name AWS::BedrockAgentCore::Runtime \
          --identifier "$runtime_id" \
          --region "$REGION" \
          --query 'ResourceDescription.Properties' --output text 2>/dev/null)
        print_info "$tier: $(echo "$details" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(f"{d[\"AgentRuntimeName\"]} status={d[\"Status\"]} platformVersion={d.get(\"PlatformVersion\",\"V1\")}")' 2>/dev/null || echo "$runtime_id")"
    fi
done

print_step "Deployment completed successfully!"
echo ""
echo "🎉 Multi-tenant AgentCore deployment is ready!"
echo ""
echo "Deployment Configuration:"
echo "  Type: direct code deployment (zip in S3)"
echo "  Python runtime: $PYTHON_RUNTIME"
echo "  Platform version: $AGENTCORE_PLATFORM_VERSION"
echo "  Runtime stack: $RUNTIME_STACK_NAME"
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