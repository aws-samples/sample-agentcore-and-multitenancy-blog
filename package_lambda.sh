#!/bin/bash
# Package Lambda with dependencies for API Gateway proxy

rm -rf lambda_package
mkdir lambda_package

# Install dependencies targeting Lambda runtime (Amazon Linux x86_64)
pip3 install -r prerequisite/lambda/python/requirements.txt -t lambda_package/ --platform manylinux2014_x86_64 --python-version 3.12 --only-binary=:all:

# Copy healthcare Lambda files
cp prerequisite/lambda/python/api_gateway_lambda.py lambda_package/
cp prerequisite/lambda/python/patient_context.py lambda_package/
cp prerequisite/lambda/python/clinic_config.py lambda_package/

# Create zip
cd lambda_package
zip -r ../lambda.zip .
cd ..

echo "Lambda package created: lambda.zip"
