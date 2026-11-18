#!/bin/bash

# Copyright (c) 2026 Amazon Web Services, Inc. All rights reserved.
# Licensed under the MIT-0 License.
#
# WARNING: This script performs DESTRUCTIVE operations that will:
# - Delete all healthcare infrastructure resources
# - Remove patient data and clinical documents
# - Cannot be undone once executed
#
# RISK ASSESSMENT: High - Permanent data loss, service disruption
# Ensure backups are complete before running this script.

# Multi-Tenant Healthcare AgentCore Cleanup Script
# Reverse order of deploy.sh to respect resource dependencies

set -e
set -o pipefail

echo "🧹 Starting Multi-Tenant Healthcare AgentCore Cleanup"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_step() { echo -e "${GREEN}[STEP]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }
print_info() { echo -e "${BLUE}[INFO]${NC} $1"; }

delete_stack() {
    local stack_name="$1"
    print_step "Deleting CloudFormation stack: $stack_name..."
    aws cloudformation delete-stack \
      --stack-name "$stack_name" \
      --region "$REGION" 2>/dev/null || {
        print_info "$stack_name does not exist."
        return
      }
    aws cloudformation wait stack-delete-complete \
      --stack-name "$stack_name" \
      --region "$REGION" 2>/dev/null || true
    print_info "$stack_name deleted (or did not exist)."
}

# ----- Config -----
BUCKET_NAME=${1:-healthcare}
INFRA_STACK_NAME=${2:-HealthcareStackInfra}
COGNITO_STACK_NAME=${3:-HealthcareStackCognito}
API_GATEWAY_STACK_NAME=${4:-HealthcareStackApiGateway}
RUNTIME_STACK_NAME=${5:-HealthcareStackRuntime}
POLICY_ENGINE_STACK_NAME=${POLICY_ENGINE_STACK_NAME:-HealthcareStackAgentCorePolicyEngine}
GATEWAY_STACK_NAME=${GATEWAY_STACK_NAME:-HealthcareStackAgentCoreGateways}
GATEWAY_TARGET_STACK_NAME=${GATEWAY_TARGET_STACK_NAME:-HealthcareStackAgentCoreGatewayTargets}
POLICY_STACK_NAME=${POLICY_STACK_NAME:-HealthcareStackAgentCorePolicies}
RATE_LIMIT_STACK_NAME=${RATE_LIMIT_STACK_NAME:-HealthcareStackAgentCoreRateLimits}
GATEWAY_OBSERVABILITY_STACK_NAME=${GATEWAY_OBSERVABILITY_STACK_NAME:-HealthcareStackAgentCoreGatewayObservability}
MEMORY_STACK_NAME=${MEMORY_STACK_NAME:-HealthcareStackAgentCoreMemory}
MEMORY_OBSERVABILITY_STACK_NAME=${MEMORY_OBSERVABILITY_STACK_NAME:-HealthcareStackAgentCoreMemoryObservability}
REGISTRY_STACK_NAME=${REGISTRY_STACK_NAME:-HealthcareStackAgentRegistry}
GUARDRAIL_STACK_NAME=${GUARDRAIL_STACK_NAME:-HealthcareStackBedrockGuardrails}
REGION=$(aws configure get region)
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
FULL_BUCKET_NAME="${BUCKET_NAME}-${ACCOUNT_ID}"

print_info "Region: $REGION"
print_info "Account: $ACCOUNT_ID"
print_info "S3 Bucket: $FULL_BUCKET_NAME"
print_info "Stacks:"
print_info "  Base: $INFRA_STACK_NAME, $COGNITO_STACK_NAME, $API_GATEWAY_STACK_NAME"
print_info "  AgentCore: $POLICY_ENGINE_STACK_NAME, $GATEWAY_STACK_NAME, $GATEWAY_TARGET_STACK_NAME"
print_info "  AgentCore: $POLICY_STACK_NAME, $RATE_LIMIT_STACK_NAME, $MEMORY_STACK_NAME"
print_info "  Supporting: $GATEWAY_OBSERVABILITY_STACK_NAME, $MEMORY_OBSERVABILITY_STACK_NAME"
print_info "  Supporting: $REGISTRY_STACK_NAME, $GUARDRAIL_STACK_NAME"
print_info "  Runtime: $RUNTIME_STACK_NAME"

# ----- Confirm Deletion -----
read -p "⚠️  Are you sure you want to tear down the entire healthcare deployment? (y/N): " confirm
if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
    echo "❌ Cleanup cancelled."
    exit 1
fi

# ----- Activate virtual environment -----
if [ -d ".venv" ]; then
    print_step "Activating virtual environment..."
    source .venv/bin/activate
else
    print_warning "No .venv found. Python scripts may fail if dependencies aren't installed globally."
fi

# ----- 1. Delete CloudFormation-owned AgentCore resources -----
# Capture retained Memory IDs and observability log group suffixes before
# deleting their stack-owned SSM parameters.
BASIC_GATEWAY_ID=$(aws ssm get-parameter \
  --name /app/healthcare/agentcore/basic_gateway_id \
  --query 'Parameter.Value' --output text 2>/dev/null || true)
PREMIUM_GATEWAY_ID=$(aws ssm get-parameter \
  --name /app/healthcare/agentcore/premium_gateway_id \
  --query 'Parameter.Value' --output text 2>/dev/null || true)
BASIC_MEMORY_ID=$(aws ssm get-parameter \
  --name /app/healthcare/memory/basic_id \
  --query 'Parameter.Value' --output text 2>/dev/null || true)
PREMIUM_MEMORY_ID=$(aws ssm get-parameter \
  --name /app/healthcare/memory/premium_id \
  --query 'Parameter.Value' --output text 2>/dev/null || true)

delete_stack "$RUNTIME_STACK_NAME"
delete_stack "$REGISTRY_STACK_NAME"
delete_stack "$GUARDRAIL_STACK_NAME"
delete_stack "$POLICY_STACK_NAME"
delete_stack "$GATEWAY_TARGET_STACK_NAME"
delete_stack "$RATE_LIMIT_STACK_NAME"
delete_stack "$GATEWAY_OBSERVABILITY_STACK_NAME"
delete_stack "$GATEWAY_STACK_NAME"
delete_stack "$POLICY_ENGINE_STACK_NAME"
delete_stack "$MEMORY_OBSERVABILITY_STACK_NAME"
delete_stack "$MEMORY_STACK_NAME"

# Observability log groups are retained by their stacks. This explicit cleanup
# path removes them only after the operator confirms the full teardown.
for resource in \
  "gateway:$BASIC_GATEWAY_ID" \
  "gateway:$PREMIUM_GATEWAY_ID" \
  "memory:$BASIC_MEMORY_ID" \
  "memory:$PREMIUM_MEMORY_ID"; do
    resource_type=${resource%%:*}
    resource_id=${resource#*:}
    if [ -n "$resource_id" ] && [ "$resource_id" != "None" ]; then
        log_group="/aws/vendedlogs/bedrock-agentcore/${resource_type}/APPLICATION_LOGS/${resource_id}"
        print_step "Deleting retained log group: $log_group..."
        aws logs delete-log-group --log-group-name "$log_group" --region "$REGION" 2>/dev/null || \
          print_info "Log group already absent: $log_group"
    fi
done

# AgentCore Memory is retained by CloudFormation to prevent accidental data
# loss. This cleanup path is explicitly destructive and has already obtained
# confirmation, so remove the retained resources by their captured IDs.
if [ -n "$BASIC_MEMORY_ID" ] && [ "$BASIC_MEMORY_ID" != "None" ]; then
    print_step "Deleting retained basic AgentCore Memory: $BASIC_MEMORY_ID..."
    python scripts/agentcore_memory.py delete --memory-id "$BASIC_MEMORY_ID" --confirm || \
      print_warning "Failed to delete retained basic memory"
fi
if [ -n "$PREMIUM_MEMORY_ID" ] && [ "$PREMIUM_MEMORY_ID" != "None" ]; then
    print_step "Deleting retained premium AgentCore Memory: $PREMIUM_MEMORY_ID..."
    python scripts/agentcore_memory.py delete --memory-id "$PREMIUM_MEMORY_ID" --confirm || \
      print_warning "Failed to delete retained premium memory"
fi

# Fallback for runtimes created by the retired starter toolkit rather than the
# runtime CloudFormation stack.
print_step "Removing any unmanaged runtimes left from a starter toolkit deploy..."
python scripts/agentcore_agent_runtime.py healthcare_basic 2>/dev/null || print_info "No unmanaged healthcare_basic runtime"
python scripts/agentcore_agent_runtime.py healthcare_premium 2>/dev/null || print_info "No unmanaged healthcare_premium runtime"

# A previous deployment may have created this deferred resource by API.
print_step "Deleting legacy Cognito credential provider, if present..."
python scripts/cognito_credentials_provider.py delete --confirm || print_info "No legacy Cognito credential provider"

# ----- 6. Delete Knowledge Bases (basic and premium) -----
print_step "Deleting Basic tier Knowledge Base..."
python prerequisite/knowledge_base.py --mode delete --config prereqs_config.yaml || print_warning "Failed to delete basic knowledge base"

print_step "Deleting Premium tier Knowledge Base..."
python prerequisite/knowledge_base.py --mode delete --config premium_prereqs_config.yaml || print_warning "Failed to delete premium knowledge base"

# ----- 7. Delete CloudFormation Stacks -----
print_step "Deleting API Gateway stack: $API_GATEWAY_STACK_NAME..."
aws cloudformation delete-stack --stack-name "$API_GATEWAY_STACK_NAME" --region "$REGION" 2>/dev/null || print_warning "API Gateway stack may not exist"
aws cloudformation wait stack-delete-complete --stack-name "$API_GATEWAY_STACK_NAME" --region "$REGION" 2>/dev/null || true
print_info "API Gateway stack deleted (or did not exist)."

print_step "Deleting Infra stack: $INFRA_STACK_NAME..."
aws cloudformation delete-stack --stack-name "$INFRA_STACK_NAME" --region "$REGION"
aws cloudformation wait stack-delete-complete --stack-name "$INFRA_STACK_NAME" --region "$REGION"
print_info "Infra stack deleted."

print_step "Deleting Cognito stack: $COGNITO_STACK_NAME..."
aws cloudformation delete-stack --stack-name "$COGNITO_STACK_NAME" --region "$REGION"
aws cloudformation wait stack-delete-complete --stack-name "$COGNITO_STACK_NAME" --region "$REGION"
print_info "Cognito stack deleted."

# ----- 8. Clean up remaining SSM parameters under /app/healthcare -----
print_step "Cleaning up remaining SSM parameters under /app/healthcare/..."
SSM_PARAMS=$(aws ssm get-parameters-by-path --path "/app/healthcare" --recursive --query 'Parameters[].Name' --output text 2>/dev/null || true)
if [ -n "$SSM_PARAMS" ]; then
    for param in $SSM_PARAMS; do
        echo "  🗑️  Deleting SSM parameter: $param"
        aws ssm delete-parameter --name "$param" 2>/dev/null || true
    done
    print_info "SSM parameters cleaned up."
else
    print_info "No remaining SSM parameters found."
fi

# ----- 9. Clean up S3 bucket -----
print_step "Cleaning S3 bucket: $FULL_BUCKET_NAME..."
aws s3 rm "s3://$FULL_BUCKET_NAME" --recursive 2>/dev/null || print_warning "Failed to clean bucket or it is already empty."

read -p "🪣 Do you want to delete the bucket '$FULL_BUCKET_NAME'? (y/N): " delete_bucket
if [[ "$delete_bucket" == "y" || "$delete_bucket" == "Y" ]]; then
    aws s3 rb "s3://$FULL_BUCKET_NAME" --force 2>/dev/null || print_warning "Failed to delete bucket"
    print_info "Bucket deleted."
else
    print_info "Bucket retained: $FULL_BUCKET_NAME"
fi

# ----- 10. Clean up local files -----
print_step "Cleaning up local files..."
rm -f lambda.zip
rm -f api_gateway_lambda.zip
rm -f .bedrock_agentcore.yaml
rm -f .agentcore.yaml
rm -f credentials/test_users.json
rm -f credentials/fhir_patient_mapping.json
print_info "Local files cleaned up."

echo ""
echo "✅ Healthcare AgentCore cleanup complete."
