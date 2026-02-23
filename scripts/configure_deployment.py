#!/usr/bin/env python3
"""
Configuration script to parameterize hardcoded values for multi-tenant deployment.
This script replaces hardcoded account IDs, ARNs, and other values with dynamic ones.
"""

import os
import sys
import boto3
import yaml
import json
import re
from pathlib import Path
from typing import Dict, Any

def get_aws_account_id() -> str:
    """Get current AWS account ID"""
    try:
        sts = boto3.client('sts')
        return sts.get_caller_identity()['Account']
    except Exception as e:
        print(f"❌ Error getting AWS account ID: {e}")
        sys.exit(1)

def get_aws_region() -> str:
    """Get current AWS region"""
    try:
        session = boto3.Session()
        return session.region_name or 'us-east-1'
    except Exception:
        return 'us-east-1'

def load_ssm_parameters() -> Dict[str, str]:
    """Load configuration from SSM Parameter Store"""
    ssm = boto3.client('ssm')
    parameters = {}
    
    try:
        # Get all parameters with the healthcare prefix
        paginator = ssm.get_paginator('get_parameters_by_path')
        for page in paginator.paginate(Path='/app/healthcare', Recursive=True):
            for param in page['Parameters']:
                # Use full path as key for nested parameters like inference_profiles/basic_arn
                key = param['Name'].replace('/app/healthcare/', '')
                parameters[key] = param['Value']
    except Exception as e:
        print(f"⚠️ Warning: Could not load SSM parameters: {e}")
    
    return parameters

def update_agent_config_files(config: Dict[str, Any]):
    """Update agent configuration files with dynamic values using regex patterns"""
    
    # Update basic agent configuration
    basic_agent_file = Path("agent_config/agent.py")
    if basic_agent_file.exists():
        content = basic_agent_file.read_text()
        
        # Replace the entire inference_profile_mapping dictionary with SSM-based loading
        # This ensures the agent loads profiles dynamically from SSM at runtime
        mapping_replacement = '''        # Get inference profile ARNs from SSM parameters
        try:
            basic_profile_arn = get_ssm_parameter("/app/healthcare/inference_profiles/basic_arn")
            premium_profile_arn = get_ssm_parameter("/app/healthcare/inference_profiles/premium_arn")
        except Exception as e:
            print(f"⚠️ Warning: Could not load inference profiles from SSM: {e}")
            print(f"   Falling back to default model: {bedrock_model_id}")
            basic_profile_arn = bedrock_model_id
            premium_profile_arn = bedrock_model_id
        
        # Map tenant to inference profile
        inference_profile_mapping = {
            "basic": basic_profile_arn,
            "premium": premium_profile_arn,
            "default": basic_profile_arn
        }'''
        
        # Replace any hardcoded inference profile mappings
        content = re.sub(
            r'# Map tenant to inference profile.*?\n.*?inference_profile_mapping = \{[^}]+\}',
            mapping_replacement,
            content,
            flags=re.DOTALL
        )
        
        basic_agent_file.write_text(content)
        print("✅ Updated basic agent configuration")
    
    # Update premium agent configuration
    premium_agent_file = Path("agent_config_premium/agent.py")
    if premium_agent_file.exists():
        content = premium_agent_file.read_text()
        
        # Replace the entire inference_profile_mapping dictionary with SSM-based loading
        mapping_replacement = '''        # Get inference profile ARNs from SSM parameters
        try:
            basic_profile_arn = get_ssm_parameter("/app/healthcare/inference_profiles/basic_arn")
            premium_profile_arn = get_ssm_parameter("/app/healthcare/inference_profiles/premium_arn")
        except Exception as e:
            print(f"⚠️ Warning: Could not load inference profiles from SSM: {e}")
            print(f"   Falling back to default model: {bedrock_model_id}")
            basic_profile_arn = bedrock_model_id
            premium_profile_arn = bedrock_model_id
        
        # Map tenant to inference profile
        inference_profile_mapping = {
            "basic": basic_profile_arn,
            "premium": premium_profile_arn,
            "default": basic_profile_arn
        }'''
        
        # Replace any hardcoded inference profile mappings
        content = re.sub(
            r'# Map tenant to inference profile.*?\n.*?inference_profile_mapping = \{[^}]+\}',
            mapping_replacement,
            content,
            flags=re.DOTALL
        )
        
        premium_agent_file.write_text(content)
        print("✅ Updated premium agent configuration")

def generate_agentcore_yaml(config: Dict[str, Any], deployment_type: str = "direct_code_deploy"):
    """Generate .bedrock_agentcore.yaml with dynamic values
    
    Args:
        config: Configuration dictionary
        deployment_type: Either "direct_code_deploy" or "container" (default: direct_code_deploy)
    
    Note: This function is now DEPRECATED for agent configuration.
    Use 'agentcore configure' CLI command instead, which will create the yaml file.
    This function is kept only for reference and backward compatibility.
    """
    
    print(f"⚠️  Skipping .bedrock_agentcore.yaml generation")
    print(f"   The 'agentcore configure' command will create this file with correct settings")
    print(f"   Deployment type will be: {deployment_type}")
    
    # Don't generate the file - let agentcore configure do it
    return

def main():
    """Main configuration function"""
    print("🔧 Configuring deployment for your AWS account...")
    
    # Check for deployment type argument
    deployment_type = "direct_code_deploy"  # Default to direct_code_deploy
    if len(sys.argv) > 1:
        if sys.argv[1] in ["container", "direct_code_deploy"]:
            deployment_type = sys.argv[1]
        else:
            print(f"⚠️ Invalid deployment type: {sys.argv[1]}")
            print("Usage: python configure_deployment.py [container|direct_code_deploy]")
            print("Defaulting to: direct_code_deploy")
    
    print(f"📦 Deployment Type: {deployment_type}")
    
    # Get AWS account information
    account_id = get_aws_account_id()
    region = get_aws_region()
    
    print(f"📋 AWS Account: {account_id}")
    print(f"📋 AWS Region: {region}")
    
    # Load SSM parameters (if available)
    ssm_params = load_ssm_parameters()
    
    # Build configuration
    config = {
        "aws": {
            "account_id": account_id,
            "region": region
        },
        "inference_profiles": {
            "basic": {
                "arn": ssm_params.get('inference_profiles/basic_arn', 
                      f"arn:aws:bedrock:{region}:{account_id}:application-inference-profile/BASIC_PROFILE_ID")
            },
            "premium": {
                "arn": ssm_params.get('inference_profiles/premium_arn',
                      f"arn:aws:bedrock:{region}:{account_id}:application-inference-profile/PREMIUM_PROFILE_ID")
            }
        },
        "cognito": {
            "user_pool_id": ssm_params.get('cognito_user_pool_id', 'COGNITO_USER_POOL_ID'),
            "client_id": ssm_params.get('web_client_id', 'COGNITO_CLIENT_ID'),
            "discovery_url": ssm_params.get('cognito_discovery_url', 
                           f"https://cognito-idp.{region}.amazonaws.com/COGNITO_USER_POOL_ID/.well-known/openid-configuration")
        },
        "agents": {
            "basic": {
                "agent_id": ssm_params.get('basic_agent_id', 'healthcare-basic-AGENT_ID'),
                "agent_arn": ssm_params.get('basic_agent_arn', 
                           f"arn:aws:bedrock-agentcore:{region}:{account_id}:runtime/healthcare-basic-AGENT_ID")
            },
            "premium": {
                "agent_id": ssm_params.get('premium_agent_id', 'healthcare-premium-AGENT_ID'),
                "agent_arn": ssm_params.get('premium_agent_arn',
                           f"arn:aws:bedrock-agentcore:{region}:{account_id}:runtime/healthcare-premium-AGENT_ID")
            }
        },
        "iam": {
            "execution_role": ssm_params.get('runtime_iam_role', 
                            f"arn:aws:iam::{account_id}:role/HealthcareStackInfra-RuntimeAgentCoreRole"),
            "codebuild_role": ssm_params.get('codebuild_iam_role',
                            f"arn:aws:iam::{account_id}:role/AmazonBedrockAgentCoreSDKCodeBuild-{region}")
        },
        "ecr": {
            "basic_repository": f"{account_id}.dkr.ecr.{region}.amazonaws.com/bedrock-agentcore-healthcare-basic",
            "premium_repository": f"{account_id}.dkr.ecr.{region}.amazonaws.com/bedrock-agentcore-healthcare-premium"
        },
        "knowledge_bases": {
            "basic": {
                "id": ssm_params.get('knowledge_base_id', 'BASIC_KB_ID')
            },
            "premium": {
                "id": ssm_params.get('premium_knowledge_base_id', 'PREMIUM_KB_ID')
            }
        }
    }
    
    # Save configuration
    os.makedirs('config', exist_ok=True)
    with open('config/deployment_config.json', 'w') as f:
        json.dump(config, f, indent=2)
    
    # Update configuration files
    update_agent_config_files(config)
    generate_agentcore_yaml(config, deployment_type)
    
    print("✅ Configuration completed!")
    print("📁 Configuration saved to: config/deployment_config.json")
    print("🚀 Ready for deployment!")

if __name__ == "__main__":
    main()