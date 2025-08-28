#!/bin/bash
# Package Lambda with dependencies

rm -rf lambda_package
mkdir lambda_package

# Install dependencies
pip3 install -r requirements_lambda.txt -t lambda_package/

# Copy Lambda code
cp api_gateway_lambda.py lambda_package/

# Create zip
cd lambda_package
zip -r ../api_gateway_lambda.zip .
cd ..

echo "Lambda package created: api_gateway_lambda.zip"
