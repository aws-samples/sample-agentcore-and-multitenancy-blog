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
        # Get all parameters with the customersupport prefix
        paginator = ssm.get_paginator('get_parameters_by_path')
        for page in paginator.paginate(Path='/app/customersupport', Recursive=True):
            for param in page['Parameters']:
                key = param['Name'].split('/')[-1]  # Get the last part of the path
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
        
        # Use regex to replace any inference profile ARNs (works regardless of account ID)
        # Pattern matches: "basic": "arn:aws:bedrock:REGION:ACCOUNT:application-inference-profile/ID"
        content = re.sub(
            r'"basic":\s*"arn:aws:bedrock:[^:]+:\d+:application-inference-profile/[^"]+',
            f'"basic": "{config["inference_profiles"]["basic"]["arn"]}',
            content
        )
        content = re.sub(
            r'"premium":\s*"arn:aws:bedrock:[^:]+:\d+:application-inference-profile/[^"]+',
            f'"premium": "{config["inference_profiles"]["premium"]["arn"]}',
            content
        )
        content = re.sub(
            r'"default":\s*"arn:aws:bedrock:[^:]+:\d+:application-inference-profile/[^"]+',
            f'"default": "{config["inference_profiles"]["basic"]["arn"]}',
            content
        )
        
        basic_agent_file.write_text(content)
        print("✅ Updated basic agent configuration")
    
    # Update premium agent configuration
    premium_agent_file = Path("agent_config_premium/agent.py")
    if premium_agent_file.exists():
        content = premium_agent_file.read_text()
        
        # Use regex to replace any inference profile ARNs
        content = re.sub(
            r'"basic":\s*"arn:aws:bedrock:[^:]+:\d+:application-inference-profile/[^"]+',
            f'"basic": "{config["inference_profiles"]["basic"]["arn"]}',
            content
        )
        content = re.sub(
            r'"premium":\s*"arn:aws:bedrock:[^:]+:\d+:application-inference-profile/[^"]+',
            f'"premium": "{config["inference_profiles"]["premium"]["arn"]}',
            content
        )
        content = re.sub(
            r'"default":\s*"arn:aws:bedrock:[^:]+:\d+:application-inference-profile/[^"]+',
            f'"default": "{config["inference_profiles"]["basic"]["arn"]}',
            content
        )
        
        premium_agent_file.write_text(content)
        print("✅ Updated premium agent configuration")

def generate_agentcore_yaml(config: Dict[str, Any]):
    """Generate .bedrock_agentcore.yaml with dynamic values"""
    
    template = {
        "default_agent": "customersupport",
        "agents": {
            "customersupport": {
                "name": "customersupport",
                "entrypoint": "main.py",
                "platform": "linux/arm64",
                "container_runtime": "finch",
                "aws": {
                    "execution_role": config['iam']['execution_role'],
                    "execution_role_auto_create": True,
                    "account": config['aws']['account_id'],
                    "region": config['aws']['region'],
                    "ecr_repository": config['ecr']['basic_repository'],
                    "ecr_auto_create": False,
                    "network_configuration": {
                        "network_mode": "PUBLIC"
                    },
                    "protocol_configuration": {
                        "server_protocol": "HTTP"
                    },
                    "observability": {
                        "enabled": True
                    }
                },
                "bedrock_agentcore": {
                    "agent_id": config['agents']['basic']['agent_id'],
                    "agent_arn": config['agents']['basic']['agent_arn'],
                    "agent_session_id": None
                },
                "codebuild": {
                    "project_name": f"bedrock-agentcore-customersupport-builder",
                    "execution_role": config['iam']['codebuild_role'],
                    "source_bucket": f"bedrock-agentcore-codebuild-sources-{config['aws']['account_id']}-{config['aws']['region']}"
                },
                "authorizer_configuration": {
                    "customJWTAuthorizer": {
                        "discoveryUrl": config['cognito']['discovery_url'],
                        "allowedClients": [config['cognito']['client_id']]
                    }
                },
                "oauth_configuration": None
            },
            "customersupport_premium": {
                "name": "customersupport_premium",
                "entrypoint": "main_premium.py",
                "platform": "linux/arm64",
                "container_runtime": "finch",
                "aws": {
                    "execution_role": config['iam']['execution_role'],
                    "execution_role_auto_create": True,
                    "account": config['aws']['account_id'],
                    "region": config['aws']['region'],
                    "ecr_repository": config['ecr']['premium_repository'],
                    "ecr_auto_create": False,
                    "network_configuration": {
                        "network_mode": "PUBLIC"
                    },
                    "protocol_configuration": {
                        "server_protocol": "HTTP"
                    },
                    "observability": {
                        "enabled": True
                    }
                },
                "bedrock_agentcore": {
                    "agent_id": config['agents']['premium']['agent_id'],
                    "agent_arn": config['agents']['premium']['agent_arn'],
                    "agent_session_id": None
                },
                "codebuild": {
                    "project_name": f"bedrock-agentcore-customersupport_premium-builder",
                    "execution_role": config['iam']['codebuild_role'],
                    "source_bucket": f"bedrock-agentcore-codebuild-sources-{config['aws']['account_id']}-{config['aws']['region']}"
                },
                "authorizer_configuration": {
                    "customJWTAuthorizer": {
                        "discoveryUrl": config['cognito']['discovery_url'],
                        "allowedClients": [config['cognito']['client_id']]
                    }
                },
                "oauth_configuration": None
            }
        }
    }
    
    with open('.bedrock_agentcore.yaml', 'w') as f:
        yaml.dump(template, f, default_flow_style=False)
    
    print("✅ Generated .bedrock_agentcore.yaml with account-specific values")

def main():
    """Main configuration function"""
    print("🔧 Configuring deployment for your AWS account...")
    
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
                "arn": ssm_params.get('basic_inference_profile_arn', 
                      f"arn:aws:bedrock:{region}:{account_id}:application-inference-profile/BASIC_PROFILE_ID")
            },
            "premium": {
                "arn": ssm_params.get('premium_inference_profile_arn',
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
                "agent_id": ssm_params.get('basic_agent_id', 'customersupport-AGENT_ID'),
                "agent_arn": ssm_params.get('basic_agent_arn', 
                           f"arn:aws:bedrock-agentcore:{region}:{account_id}:runtime/customersupport-AGENT_ID")
            },
            "premium": {
                "agent_id": ssm_params.get('premium_agent_id', 'customersupport_premium-AGENT_ID'),
                "agent_arn": ssm_params.get('premium_agent_arn',
                           f"arn:aws:bedrock-agentcore:{region}:{account_id}:runtime/customersupport_premium-AGENT_ID")
            }
        },
        "iam": {
            "execution_role": ssm_params.get('runtime_iam_role', 
                            f"arn:aws:iam::{account_id}:role/CustomerSupportStackInfra-RuntimeAgentCoreRole"),
            "codebuild_role": ssm_params.get('codebuild_iam_role',
                            f"arn:aws:iam::{account_id}:role/AmazonBedrockAgentCoreSDKCodeBuild-{region}")
        },
        "ecr": {
            "basic_repository": f"{account_id}.dkr.ecr.{region}.amazonaws.com/bedrock-agentcore-customersupport",
            "premium_repository": f"{account_id}.dkr.ecr.{region}.amazonaws.com/bedrock-agentcore-customersupport_premium"
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
    generate_agentcore_yaml(config)
    
    print("✅ Configuration completed!")
    print("📁 Configuration saved to: config/deployment_config.json")
    print("🚀 Ready for deployment!")

if __name__ == "__main__":
    main()