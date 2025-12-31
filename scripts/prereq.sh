#!/bin/bash

set -e
set -o pipefail

# ----- Config -----
BUCKET_NAME=${1:-healthcare}
INFRA_STACK_NAME=${2:-HealthcareStackInfra}
COGNITO_STACK_NAME=${3:-HealthcareStackCognito}
API_GATEWAY_STACK_NAME=${4:-HealthcareStackApiGateway}
INFRA_TEMPLATE_FILE="prerequisite/infrastructure.yaml"
COGNITO_TEMPLATE_FILE="prerequisite/cognito.yaml"
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

# ----- 2. Zip Lambda code -----
echo "📦 Zipping contents of $LAMBDA_SRC into $ZIP_FILE..."
cd "$LAMBDA_SRC"
zip -r "../../../$ZIP_FILE" . > /dev/null
cd - > /dev/null

# ----- 2b. Zip API Gateway Lambda code -----
echo "📦 Zipping API Gateway Lambda code into $API_GATEWAY_ZIP_FILE..."
if [ -f "prerequisite/lambda/python/api_gateway_lambda.py" ]; then
  cd "prerequisite/lambda/python"
  zip "../../../$API_GATEWAY_ZIP_FILE" api_gateway_lambda.py > /dev/null
  cd - > /dev/null
else
  echo "⚠️  API Gateway Lambda code not found, skipping..."
fi

# ----- 3. Upload to S3 -----
echo "☁️ Uploading $ZIP_FILE to s3://$FULL_BUCKET_NAME/$S3_KEY..."
aws s3 cp "$ZIP_FILE" "s3://$FULL_BUCKET_NAME/$S3_KEY"

if [ -f "$API_GATEWAY_ZIP_FILE" ]; then
  echo "☁️ Uploading $API_GATEWAY_ZIP_FILE to s3://$FULL_BUCKET_NAME/$API_GATEWAY_S3_KEY..."
  aws s3 cp "$API_GATEWAY_ZIP_FILE" "s3://$FULL_BUCKET_NAME/$API_GATEWAY_S3_KEY"
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
  deploy_stack "$API_GATEWAY_STACK_NAME" "$API_GATEWAY_TEMPLATE_FILE" --parameter-overrides LambdaCodeBucket="$FULL_BUCKET_NAME" LambdaCodeKey="$API_GATEWAY_S3_KEY"
  api_gateway_exit_code=$?
else
  echo "⚠️  Skipping API Gateway stack deployment (Lambda code not found)"
  api_gateway_exit_code=0
fi

echo "🏥 Checking for healthcare documents..."
if [ ! -d "prerequisite/basic-documents" ] || [ ! -d "prerequisite/premium-documents" ]; then
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

# ----- 6. Create Knowledge Base -----

python prerequisite/knowledge_base.py --mode create

echo "✅ Deployment complete."
