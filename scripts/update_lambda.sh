#!/bin/bash

# Script to update the API Gateway Lambda function

set -e

echo "📦 Packaging Lambda function..."

# Create a temporary directory for packaging
TEMP_DIR=$(mktemp -d)
echo "Using temp directory: $TEMP_DIR"

# Copy Lambda code
cp prerequisite/lambda/python/*.py "$TEMP_DIR/"

# Install dependencies if needed
if [ -f "prerequisite/lambda/python/requirements.txt" ]; then
    pip install -r prerequisite/lambda/python/requirements.txt -t "$TEMP_DIR/"
else
    # Install requests library (required by the Lambda)
    pip install requests -t "$TEMP_DIR/"
fi

# Create zip file
cd "$TEMP_DIR"
zip -r lambda.zip .
cd -

# Move zip to project root
mv "$TEMP_DIR/lambda.zip" api_gateway_lambda.zip

# Clean up
rm -rf "$TEMP_DIR"

echo "✅ Lambda package created: api_gateway_lambda.zip"

# Update Lambda function
echo "🚀 Updating Lambda function..."
aws lambda update-function-code \
    --function-name agentcore-api-gateway-proxy \
    --zip-file fileb://api_gateway_lambda.zip \
    --region us-east-1

echo "✅ Lambda function updated successfully!"

# Wait for update to complete
echo "⏳ Waiting for Lambda update to complete..."
aws lambda wait function-updated \
    --function-name agentcore-api-gateway-proxy \
    --region us-east-1

echo "🎉 Lambda function is ready!"
