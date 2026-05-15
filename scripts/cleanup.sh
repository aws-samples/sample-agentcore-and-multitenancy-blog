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

# ----- Config -----
BUCKET_NAME=${1:-healthcare}
INFRA_STACK_NAME=${2:-HealthcareStackInfra}
COGNITO_STACK_NAME=${3:-HealthcareStackCognito}
API_GATEWAY_STACK_NAME=${4:-HealthcareStackApiGateway}
REGION=$(aws configure get region)
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
FULL_BUCKET_NAME="${BUCKET_NAME}-${ACCOUNT_ID}"

print_info "Region: $REGION"
print_info "Account: $ACCOUNT_ID"
print_info "S3 Bucket: $FULL_BUCKET_NAME"
print_info "Stacks: $INFRA_STACK_NAME, $COGNITO_STACK_NAME, $API_GATEWAY_STACK_NAME"

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

# ----- 1. Delete AgentCore Agent Runtimes -----
print_step "Deleting AgentCore agent runtimes..."
python scripts/agentcore_agent_runtime.py healthcare_basic || print_warning "Failed to delete healthcare_basic runtime (may not exist)"
python scripts/agentcore_agent_runtime.py healthcare_premium || print_warning "Failed to delete healthcare_premium runtime (may not exist)"

# ----- 2. Delete AgentCore Memory Resources -----
print_step "Deleting AgentCore Memory resources (basic and premium)..."
python scripts/agentcore_memory.py delete-all --confirm || print_warning "Failed to delete memory resources"

# ----- 3. Delete Cognito Credential Provider -----
print_step "Deleting Cognito credential provider..."
python scripts/cognito_credentials_provider.py delete --confirm || print_warning "Failed to delete Cognito credential provider"

print_step "Deleting FHIR OBO credential provider..."
python scripts/fhir_credential_provider.py delete --confirm || print_warning "Failed to delete FHIR OBO credential provider"

print_step "Scheduling FHIR signing KMS key for deletion..."
FHIR_KEY_ID=$(aws ssm get-parameter --name /app/healthcare/fhir/signing_key_id --query 'Parameter.Value' --output text 2>/dev/null || echo "")
if [ -n "$FHIR_KEY_ID" ] && [ "$FHIR_KEY_ID" != "None" ]; then
    aws kms schedule-key-deletion --key-id "$FHIR_KEY_ID" --pending-window-in-days 7 2>/dev/null || print_warning "Could not schedule KMS key deletion"
    aws kms delete-alias --alias-name alias/healthcare-fhir-signing 2>/dev/null || true
    print_info "KMS key $FHIR_KEY_ID scheduled for deletion (7-day waiting period)"
else
    print_info "No FHIR signing key found in SSM"
fi

# ----- 4. Delete AgentCore Policy Engine -----
print_step "Deleting AgentCore Policy Engine..."
python scripts/agentcore_policy.py delete --confirm || print_warning "Failed to delete policy engine"

# ----- 5. Delete AgentCore Gateways -----
print_step "Deleting AgentCore Gateways (basic and premium)..."
python scripts/agentcore_gateway.py delete-all --confirm || print_warning "Failed to delete gateways"

# ----- 5b. Delete Bedrock Guardrails -----
print_step "Deleting Bedrock Guardrails (basic and premium)..."
python scripts/bedrock_guardrails.py delete --confirm || print_warning "Failed to delete guardrails"

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

print_step "Deleting FHIR MCP API Gateway stack: HealthcareStackFhirApi..."
aws cloudformation delete-stack --stack-name "HealthcareStackFhirApi" --region "$REGION" 2>/dev/null || print_warning "FHIR API stack may not exist"
aws cloudformation wait stack-delete-complete --stack-name "HealthcareStackFhirApi" --region "$REGION" 2>/dev/null || true
print_info "FHIR API Gateway stack deleted (or did not exist)."

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
rm -f fhir_mcp_lambda.zip
rm -f .bedrock_agentcore.yaml
rm -f .agentcore.yaml
rm -f credentials/test_users.json
rm -f credentials/fhir_patient_mapping.json
print_info "Local files cleaned up."

echo ""
echo "✅ Healthcare AgentCore cleanup complete."
