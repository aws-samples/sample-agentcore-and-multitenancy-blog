#!/bin/bash
# Package Lambda with dependencies

rm -rf lambda_package
mkdir lambda_package

# Install dependencies
pip3 install -r requirements_lambda.txt -t lambda_package/

# Copy only CustomerSupportLambda files
cp prerequisite/lambda/python/lambda_function.py lambda_package/
cp prerequisite/lambda/python/get_customer_profile.py lambda_package/
cp prerequisite/lambda/python/check_warranty.py lambda_package/
cp prerequisite/lambda/python/get_client_profile.py lambda_package/
cp prerequisite/lambda/python/get_portfolio_summary.py lambda_package/

# Create zip
cd lambda_package
zip -r ../lambda.zip .
cd ..

echo "Lambda package created: lambda.zip"
