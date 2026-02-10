#!/bin/bash

# Fix API Key SSM Parameters
# CloudFormation's !Ref on AWS::ApiGateway::ApiKey returns the key's resource ID,
# not the actual secret key value. This script fetches the real values and updates SSM.

set -e

API_GATEWAY_STACK_NAME=${1:-HealthcareStackApiGateway}

echo "🔑 Fixing API Key SSM parameters..."

# Get the API Key resource IDs from CloudFormation
PREMIUM_KEY_ID=$(aws cloudformation describe-stack-resource \
    --stack-name "$API_GATEWAY_STACK_NAME" \
    --logical-resource-id PremiumApiKey \
    --query 'StackResourceDetail.PhysicalResourceId' \
    --output text 2>/dev/null)

BASIC_KEY_ID=$(aws cloudformation describe-stack-resource \
    --stack-name "$API_GATEWAY_STACK_NAME" \
    --logical-resource-id BasicApiKey \
    --query 'StackResourceDetail.PhysicalResourceId' \
    --output text 2>/dev/null)

if [ -z "$PREMIUM_KEY_ID" ] || [ -z "$BASIC_KEY_ID" ]; then
    echo "❌ Could not retrieve API Key resource IDs from stack $API_GATEWAY_STACK_NAME"
    exit 1
fi

echo "  Premium Key ID: $PREMIUM_KEY_ID"
echo "  Basic Key ID:   $BASIC_KEY_ID"

# Fetch the actual API key values (the secret sent in x-api-key header)
PREMIUM_KEY_VALUE=$(aws apigateway get-api-key \
    --api-key "$PREMIUM_KEY_ID" \
    --include-value \
    --query 'value' \
    --output text)

BASIC_KEY_VALUE=$(aws apigateway get-api-key \
    --api-key "$BASIC_KEY_ID" \
    --include-value \
    --query 'value' \
    --output text)

if [ -z "$PREMIUM_KEY_VALUE" ] || [ -z "$BASIC_KEY_VALUE" ]; then
    echo "❌ Could not retrieve actual API key values"
    exit 1
fi

# Update SSM with the real key values
aws ssm put-parameter \
    --name /app/healthcare/agentcore/premium_api_key \
    --value "$PREMIUM_KEY_VALUE" \
    --type String \
    --overwrite

aws ssm put-parameter \
    --name /app/healthcare/agentcore/basic_api_key \
    --value "$BASIC_KEY_VALUE" \
    --type String \
    --overwrite

echo "✅ API Key SSM parameters updated with actual key values"
