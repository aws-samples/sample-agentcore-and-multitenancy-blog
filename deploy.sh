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
POLICY_ENGINE_STACK_NAME="${POLICY_ENGINE_STACK_NAME:-HealthcareStackAgentCorePolicyEngine}"
GATEWAY_STACK_NAME="${GATEWAY_STACK_NAME:-HealthcareStackAgentCoreGateways}"
GATEWAY_TARGET_STACK_NAME="${GATEWAY_TARGET_STACK_NAME:-HealthcareStackAgentCoreGatewayTargets}"
POLICY_STACK_NAME="${POLICY_STACK_NAME:-HealthcareStackAgentCorePolicies}"
RATE_LIMIT_STACK_NAME="${RATE_LIMIT_STACK_NAME:-HealthcareStackAgentCoreRateLimits}"
GATEWAY_OBSERVABILITY_STACK_NAME="${GATEWAY_OBSERVABILITY_STACK_NAME:-HealthcareStackAgentCoreGatewayObservability}"
MEMORY_STACK_NAME="${MEMORY_STACK_NAME:-HealthcareStackAgentCoreMemory}"
MEMORY_OBSERVABILITY_STACK_NAME="${MEMORY_OBSERVABILITY_STACK_NAME:-HealthcareStackAgentCoreMemoryObservability}"
REGISTRY_STACK_NAME="${REGISTRY_STACK_NAME:-HealthcareStackAgentRegistry}"
GUARDRAIL_STACK_NAME="${GUARDRAIL_STACK_NAME:-HealthcareStackBedrockGuardrails}"
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

# Deploy one CloudFormation-owned AgentCore component. Each component uses its
# own stack so it can be updated or rolled back without replacing unrelated
# resources. Cross-stack dependencies are passed through SSM parameters.
deploy_component_stack() {
    local stack_name="$1"
    local template_file="$2"
    shift 2

    print_step "Deploying stack ${stack_name}..."
    aws cloudformation deploy \
      --stack-name "$stack_name" \
      --template-file "$template_file" \
      --region "$REGION" \
      --no-fail-on-empty-changeset \
      "$@"
}

# AgentCore trace delivery to X-Ray requires CloudWatch Logs as the account's
# trace segment destination. This is an account-level setting rather than an
# AgentCore resource, and CloudFormation cannot safely adopt it when it is
# already enabled, so keep this single idempotent control-plane call.
ensure_xray_cloudwatch_destination() {
    local destination
    local status
    destination=$(aws xray get-trace-segment-destination \
      --region "$REGION" --query 'Destination' --output text 2>/dev/null || true)
    status=$(aws xray get-trace-segment-destination \
      --region "$REGION" --query 'Status' --output text 2>/dev/null || true)

    if [ "$destination" = "CloudWatchLogs" ] && [ "$status" = "ACTIVE" ]; then
        print_info "CloudWatch Logs is already the active X-Ray trace destination."
        return
    fi

    print_step "Enabling CloudWatch Logs as the X-Ray trace destination..."
    aws xray update-trace-segment-destination \
      --destination CloudWatchLogs \
      --region "$REGION" >/dev/null
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

print_warning "Please ensure all resource names are prefixed with 'healthcare'"

# ----------------------------------------------------------------------------
# AgentCore control-plane resources (infrastructure as code)
#
# Each resource category has a separate stack. The deployment order follows
# the actual dependencies: policy engine -> gateways -> targets -> policies.
# Memory and Registry use their own stacks. The OAuth2 credential provider is
# intentionally deferred until its usage and secret source are confirmed.
# ----------------------------------------------------------------------------

deploy_component_stack \
  "$POLICY_ENGINE_STACK_NAME" \
  prerequisite/agentcore_policy_engine.yaml

deploy_component_stack \
  "$GATEWAY_STACK_NAME" \
  prerequisite/agentcore_gateways.yaml

deploy_component_stack \
  "$GATEWAY_TARGET_STACK_NAME" \
  prerequisite/agentcore_gateway_targets.yaml

deploy_component_stack \
  "$POLICY_STACK_NAME" \
  prerequisite/agentcore_policies.yaml

deploy_component_stack \
  "$RATE_LIMIT_STACK_NAME" \
  prerequisite/agentcore_gateway_rate_limits.yaml

ensure_xray_cloudwatch_destination

deploy_component_stack \
  "$GATEWAY_OBSERVABILITY_STACK_NAME" \
  prerequisite/agentcore_gateway_observability.yaml

REGISTRY_RECORD_TIMESTAMP=$(/bin/date -u +"%Y-%m-%dT%H:%M:%SZ")
deploy_component_stack \
  "$REGISTRY_STACK_NAME" \
  prerequisite/agent_registry.yaml \
  --parameter-overrides RecordTimestamp="$REGISTRY_RECORD_TIMESTAMP"

# AWS::AgentRegistry::RegistryRecord creates a DRAFT revision. Submission is a
# separate Agent Registry lifecycle operation with no CloudFormation property.
# The stack's APPROVE_ALL rule approves each submitted revision automatically.
print_step "Submitting Agent Registry records for approval..."
python scripts/registry_publisher.py

deploy_component_stack \
  "$MEMORY_STACK_NAME" \
  prerequisite/agentcore_memory.yaml

deploy_component_stack \
  "$MEMORY_OBSERVABILITY_STACK_NAME" \
  prerequisite/agentcore_memory_observability.yaml

deploy_component_stack \
  "$GUARDRAIL_STACK_NAME" \
  prerequisite/bedrock_guardrails.yaml

# The AgentCore OAuth2 credential provider is intentionally not created here.
# It is currently unused, and its Cognito client secret source requires a
# separate design decision before it can be managed safely by CloudFormation.

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

deploy_component_stack \
  "$RUNTIME_STACK_NAME" \
  prerequisite/agentcore_runtime.yaml \
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

print_step "Listing deployed SSM parameters..."
chmod +x scripts/list_ssm_parameters.sh
./scripts/list_ssm_parameters.sh

print_step "Deployment completed successfully!"
echo ""
echo "🎉 Multi-tenant AgentCore deployment is ready!"
echo ""
echo "Deployment Configuration:"
echo "  Type: direct code deployment (zip in S3)"
echo "  Python runtime: $PYTHON_RUNTIME"
echo "  Platform version: $AGENTCORE_PLATFORM_VERSION"
echo "  Policy engine stack: $POLICY_ENGINE_STACK_NAME"
echo "  Gateway stack: $GATEWAY_STACK_NAME"
echo "  Gateway target stack: $GATEWAY_TARGET_STACK_NAME"
echo "  Policy stack: $POLICY_STACK_NAME"
echo "  Rate limit stack: $RATE_LIMIT_STACK_NAME"
echo "  Memory stack: $MEMORY_STACK_NAME"
echo "  Guardrail stack: $GUARDRAIL_STACK_NAME"
echo "  Registry stack: $REGISTRY_STACK_NAME"
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