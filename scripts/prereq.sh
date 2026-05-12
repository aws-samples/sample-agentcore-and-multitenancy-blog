#!/bin/bash

set -e
set -o pipefail

# ----- Config -----
BUCKET_NAME=${1:-healthcare}
INFRA_STACK_NAME=${2:-HealthcareStackInfra}
COGNITO_STACK_NAME=${3:-HealthcareStackCognito}
API_GATEWAY_STACK_NAME=${4:-HealthcareStackApiGateway}
INFRA_TEMPLATE_FILE="prerequisite/infrastructure.yaml"
COGNITO_TEMPLATE_FILE="prerequisite/cognito_multitenant.yaml"
API_GATEWAY_TEMPLATE_FILE="prerequisite/api_gateway_template.yaml"
REGION=$(aws configure get region)
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
FULL_BUCKET_NAME="${BUCKET_NAME}-${ACCOUNT_ID}"
ZIP_FILE="lambda.zip"
API_GATEWAY_ZIP_FILE="api_gateway_lambda.zip"
LAMBDA_SRC="prerequisite/lambda/python"
S3_KEY="${ZIP_FILE}"
API_GATEWAY_S3_KEY="${API_GATEWAY_ZIP_FILE}"

# ----- 1. Create S3 bucket -----
echo "🪣 Using S3 bucket: $FULL_BUCKET_NAME"
if [ "$REGION" = "us-east-1" ]; then
  aws s3api create-bucket \
    --bucket "$FULL_BUCKET_NAME" \
    2>/dev/null || echo "ℹ️ Bucket may already exist or be owned by you."
else
  aws s3api create-bucket \
    --bucket "$FULL_BUCKET_NAME" \
    --region "$REGION" \
    --create-bucket-configuration LocationConstraint="$REGION" \
    2>/dev/null || echo "ℹ️ Bucket may already exist or be owned by you."
fi

# ----- 2. Zip Lambda code (CustomerSupport Lambda - no external dependencies needed) -----
echo "📦 Zipping contents of $LAMBDA_SRC into $ZIP_FILE..."
cd "$LAMBDA_SRC"
zip -r "../../../$ZIP_FILE" lambda_function.py patient_context.py clinic_config.py > /dev/null
cd - > /dev/null

# ----- 2b. Zip API Gateway Lambda code with dependencies -----
echo "📦 Packaging API Gateway Lambda with dependencies into $API_GATEWAY_ZIP_FILE..."
if [ -f "prerequisite/lambda/python/api_gateway_lambda.py" ]; then
  rm -rf api_gw_lambda_package
  mkdir api_gw_lambda_package
  pip3 install -r prerequisite/lambda/python/requirements.txt -t api_gw_lambda_package/ --platform manylinux2014_x86_64 --python-version 3.12 --only-binary=:all: --quiet
  cp prerequisite/lambda/python/api_gateway_lambda.py api_gw_lambda_package/
  cd api_gw_lambda_package
  zip -r "../$API_GATEWAY_ZIP_FILE" . > /dev/null
  cd - > /dev/null
  rm -rf api_gw_lambda_package
else
  echo "⚠️  API Gateway Lambda code not found, skipping..."
fi

# ----- 2c. Zip FHIR MCP Lambda code with dependencies -----
FHIR_LAMBDA_ZIP_FILE="fhir_mcp_lambda.zip"
echo "📦 Packaging FHIR MCP Lambda with dependencies into $FHIR_LAMBDA_ZIP_FILE..."
if [ -f "prerequisite/lambda/python/fhir_mcp_lambda.py" ]; then
  rm -rf fhir_lambda_package
  mkdir fhir_lambda_package
  pip3 install PyJWT requests cryptography -t fhir_lambda_package/ --platform manylinux2014_x86_64 --python-version 3.12 --only-binary=:all: --quiet
  cp prerequisite/lambda/python/fhir_mcp_lambda.py fhir_lambda_package/
  cd fhir_lambda_package
  zip -r "../$FHIR_LAMBDA_ZIP_FILE" . > /dev/null
  cd - > /dev/null
  rm -rf fhir_lambda_package
else
  echo "⚠️  FHIR MCP Lambda code not found, skipping..."
fi

# ----- 3. Upload to S3 -----
echo "☁️ Uploading $ZIP_FILE to s3://$FULL_BUCKET_NAME/$S3_KEY..."
aws s3 cp "$ZIP_FILE" "s3://$FULL_BUCKET_NAME/$S3_KEY"

if [ -f "$API_GATEWAY_ZIP_FILE" ]; then
  echo "☁️ Uploading $API_GATEWAY_ZIP_FILE to s3://$FULL_BUCKET_NAME/$API_GATEWAY_S3_KEY..."
  aws s3 cp "$API_GATEWAY_ZIP_FILE" "s3://$FULL_BUCKET_NAME/$API_GATEWAY_S3_KEY"
fi

if [ -f "$FHIR_LAMBDA_ZIP_FILE" ]; then
  echo "☁️ Uploading $FHIR_LAMBDA_ZIP_FILE to s3://$FULL_BUCKET_NAME/$FHIR_LAMBDA_ZIP_FILE..."
  aws s3 cp "$FHIR_LAMBDA_ZIP_FILE" "s3://$FULL_BUCKET_NAME/$FHIR_LAMBDA_ZIP_FILE"
fi

# ----- 4. Deploy CloudFormation -----
deploy_stack() {
  set +e

  local stack_name=$1
  local template_file=$2
  shift 2
  local params=("$@")

  echo "🚀 Deploying CloudFormation stack: $stack_name"

  output=$(aws cloudformation deploy \
    --stack-name "$stack_name" \
    --template-file "$template_file" \
    --capabilities CAPABILITY_NAMED_IAM \
    --region "$REGION" \
    "${params[@]}" 2>&1)

  exit_code=$?

  echo "$output"

  if [ $exit_code -ne 0 ]; then
    if echo "$output" | grep -qi "No changes to deploy"; then
      echo "ℹ️ No updates for stack $stack_name, continuing..."
      return 0
    else
      echo "❌ Error deploying stack $stack_name:"
      echo "$output"
      return $exit_code
    fi
  else
    echo "✅ Stack $stack_name deployed successfully."
    return 0
  fi
}

# ----- Run all stacks -----
echo "🔧 Starting deployment of infrastructure stack..."
deploy_stack "$INFRA_STACK_NAME" "$INFRA_TEMPLATE_FILE" --parameter-overrides LambdaS3Bucket="$FULL_BUCKET_NAME" LambdaS3Key="$S3_KEY"
infra_exit_code=$?

echo "🔧 Starting deployment of Cognito stack..."
deploy_stack "$COGNITO_STACK_NAME" "$COGNITO_TEMPLATE_FILE"
cognito_exit_code=$?

echo "🔧 Starting deployment of API Gateway stack..."
if [ -f "$API_GATEWAY_ZIP_FILE" ]; then
  deploy_stack "$API_GATEWAY_STACK_NAME" "$API_GATEWAY_TEMPLATE_FILE" \
    --parameter-overrides \
      LambdaCodeBucket="$FULL_BUCKET_NAME" \
      LambdaCodeKey="$API_GATEWAY_S3_KEY"
  api_gateway_exit_code=$?

  if [ $api_gateway_exit_code -eq 0 ]; then
    echo "🔑 Fixing API Key SSM parameters (CloudFormation stores key ID, not actual value)..."
    chmod +x scripts/fix_api_key_ssm.sh
    ./scripts/fix_api_key_ssm.sh "$API_GATEWAY_STACK_NAME"
  fi
else
  echo "⚠️  Skipping API Gateway stack deployment (Lambda code not found)"
  api_gateway_exit_code=0
fi

# ----- Deploy FHIR MCP API Gateway stack -----
FHIR_STACK_NAME="HealthcareStackFhirApi"
FHIR_TEMPLATE_FILE="prerequisite/fhir_api_gateway_template.yaml"
echo "🔧 Starting deployment of FHIR MCP API Gateway stack..."
if [ -f "$FHIR_LAMBDA_ZIP_FILE" ]; then
  # Get Cognito User Pool ID for JWT validation
  COGNITO_USER_POOL_ID=$(aws ssm get-parameter --name /app/healthcare/agentcore/user_pool_id --query 'Parameter.Value' --output text 2>/dev/null || echo "")
  if [ -z "$COGNITO_USER_POOL_ID" ]; then
    echo "⚠️  Cognito User Pool ID not found in SSM, FHIR JWT validation will use fallback mode"
    COGNITO_USER_POOL_ID="not-configured"
  fi

  deploy_stack "$FHIR_STACK_NAME" "$FHIR_TEMPLATE_FILE" \
    --parameter-overrides \
      LambdaCodeBucket="$FULL_BUCKET_NAME" \
      LambdaCodeKey="$FHIR_LAMBDA_ZIP_FILE" \
      CognitoUserPoolId="$COGNITO_USER_POOL_ID" \
      CognitoRegion="$REGION"
  fhir_exit_code=$?

  if [ $fhir_exit_code -eq 0 ]; then
    echo "✅ FHIR MCP API Gateway deployed successfully"
  fi
else
  echo "⚠️  Skipping FHIR API Gateway stack deployment (Lambda code not found)"
fi

echo "🏥 Checking for healthcare documents..."
# Check if directories contain files
if [ -z "$(ls -A prerequisite/basic-documents 2>/dev/null)" ] || \
   [ -z "$(ls -A prerequisite/premium-documents 2>/dev/null)" ]; then
  echo "📝 Generating synthetic healthcare documents..."
  echo "   Using Claude Sonnet 4.5 (~213 documents, estimated cost: ~$1.67)"
  python scripts/generate_healthcare_documents.py
  
  if [ $? -ne 0 ]; then
    echo "❌ Document generation failed. Check AWS credentials and Bedrock access."
    exit 1
  fi
else
  echo "✅ Healthcare documents found, skipping generation"
fi

echo "🔍 Fetching Knowledge Base and Data Source IDs from SSM..."

# ----- 6. Create Knowledge Bases (Basic and Premium) -----

echo "📚 Creating Basic Tier Knowledge Base..."
python prerequisite/knowledge_base.py --mode create --config prereqs_config.yaml

echo "📚 Creating Premium Tier Knowledge Base..."
python prerequisite/knowledge_base.py --mode create --config premium_prereqs_config.yaml

echo "✅ Deployment complete."
