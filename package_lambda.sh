#!/bin/bash
# Package Lambda with dependencies for API Gateway proxy

rm -rf lambda_package
mkdir lambda_package

# Install dependencies
pip3 install -r requirements_lambda.txt -t lambda_package/

# Copy healthcare Lambda files
cp prerequisite/lambda/python/api_gateway_lambda.py lambda_package/
cp prerequisite/lambda/python/patient_context.py lambda_package/
cp prerequisite/lambda/python/clinic_config.py lambda_package/

# Create zip
cd lambda_package
zip -r ../lambda.zip .
cd ..

echo "Lambda package created: lambda.zip"
