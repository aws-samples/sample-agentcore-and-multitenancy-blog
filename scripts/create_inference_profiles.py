#!/usr/bin/env python3
"""
Create Bedrock inference profiles for multi-tenant deployment.
This script creates separate inference profiles for basic and premium tiers.
"""

import boto3
import json
import sys
from botocore.exceptions import ClientError

def create_inference_profile(bedrock_client, profile_name: str, model_id: str = "us.anthropic.claude-3-7-sonnet-20250219-v1:0"):
    """Create a Bedrock inference profile"""
    try:
        response = bedrock_client.create_application_inference_profile(
            inferenceProfileName=profile_name,
            description=f"Inference profile for {profile_name} tier customer support",
            modelSource={
                'copyFrom': model_id
            },
            tags=[
                {
                    'key': 'Project',
                    'value': 'CustomerSupport'
                },
                {
                    'key': 'Tier',
                    'value': profile_name.title()
                }
            ]
        )
        
        profile_arn = response['inferenceProfileArn']
        print(f"✅ Created inference profile: {profile_name}")
        print(f"   ARN: {profile_arn}")
        return profile_arn
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConflictException':
            print(f"⚠️ Inference profile {profile_name} already exists")
            # Get existing profile ARN
            try:
                response = bedrock_client.get_application_inference_profile(
                    inferenceProfileIdentifier=profile_name
                )
                return response['inferenceProfileArn']
            except ClientError:
                print(f"❌ Could not retrieve existing profile {profile_name}")
                return None
        else:
            print(f"❌ Error creating inference profile {profile_name}: {e}")
            return None

def store_profile_arn_in_ssm(ssm_client, param_name: str, profile_arn: str):
    """Store inference profile ARN in SSM Parameter Store"""
    try:
        ssm_client.put_parameter(
            Name=param_name,
            Value=profile_arn,
            Type='String',
            Overwrite=True,
            Description=f'Inference profile ARN for {param_name}'
        )
        print(f"✅ Stored {param_name} in SSM Parameter Store")
    except ClientError as e:
        print(f"❌ Error storing {param_name} in SSM: {e}")

def main():
    """Main function to create inference profiles"""
    print("🧠 Creating Bedrock inference profiles for multi-tenant deployment...")
    
    try:
        # Initialize AWS clients
        bedrock_client = boto3.client('bedrock')
        ssm_client = boto3.client('ssm')
        
        # Create basic tier inference profile
        basic_profile_arn = create_inference_profile(
            bedrock_client, 
            "customersupport-basic-profile"
        )
        
        if basic_profile_arn:
            store_profile_arn_in_ssm(
                ssm_client,
                "/app/customersupport/inference_profiles/basic_arn",
                basic_profile_arn
            )
        
        # Create premium tier inference profile
        premium_profile_arn = create_inference_profile(
            bedrock_client,
            "customersupport-premium-profile"
        )
        
        if premium_profile_arn:
            store_profile_arn_in_ssm(
                ssm_client,
                "/app/customersupport/inference_profiles/premium_arn", 
                premium_profile_arn
            )
        
        print("✅ Inference profile creation completed!")
        
        # Update configuration
        print("🔧 Updating deployment configuration...")
        import subprocess
        subprocess.run([sys.executable, "scripts/configure_deployment.py"], check=True)
        
    except Exception as e:
        print(f"❌ Error in inference profile creation: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()