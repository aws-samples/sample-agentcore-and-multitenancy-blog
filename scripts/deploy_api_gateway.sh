#!/bin/bash

# Deploy API Gateway for AgentCore multitenancy
set -e

STACK_NAME="agentcore-multitenant-api"
REGION="us-east-1"
BUCKET_NAME="agentcore-lambda"

echo "Deploying API Gateway for AgentCore multitenancy..."

# Create Lambda deployment package
echo "Creating Lambda deployment package..."
zip -r api_gateway_lambda.zip api_gateway_lambda.py

# Upload to S3
echo "Uploading Lambda code to S3..."
aws s3 cp api_gateway_lambda.zip s3://$BUCKET_NAME/

# Deploy CloudFormation stack
echo "Deploying CloudFormation stack..."
aws cloudformation deploy \
    --template-file api_gateway_template.yaml \
    --stack-name $STACK_NAME \
    --parameter-overrides \
        LambdaCodeBucket=$BUCKET_NAME \
        LambdaCodeKey=api_gateway_lambda.zip \
    --capabilities CAPABILITY_IAM \
    --region $REGION

# Get API Gateway URL
API_GATEWAY_URL=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --region $REGION \
    --query 'Stacks[0].Outputs[?OutputKey==`ApiGatewayUrl`].OutputValue' \
    --output text)

echo "API Gateway deployed successfully!"
echo "API Gateway URL: $API_GATEWAY_URL"
echo ""
echo "To use the new architecture:"
echo "1. Set environment variable: export API_GATEWAY_URL=$API_GATEWAY_URL"
echo "2. Update your Streamlit app to use chat_with_api_gateway.py"
echo "3. Configure tenant IDs in Cognito user attributes (custom:tenant_id)"

# Clean up
rm api_gateway_lambda.zip
