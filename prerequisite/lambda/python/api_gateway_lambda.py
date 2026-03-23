# Copyright 2026 Amazon.com and its affiliates; all rights reserved.
# SPDX-License-Identifier: MIT-0

import json
import urllib.parse
import requests
import boto3
import os
from typing import Dict, Any

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    API Gateway Lambda proxy to AgentCore with tenant-based throttling
    """
    try:
        print(f"Received event: {json.dumps(event)}")
        
        # Extract tenant info (tier, clinic_id, and user_id) from JWT token or headers
        tenant_info = extract_tenant_info(event)
        tier = tenant_info['tier']
        clinic_id = tenant_info['clinic_id']
        user_id = tenant_info['user_id']
        print(f"Tier: {tier}, Clinic ID: {clinic_id}, User ID: {user_id}")
        
        # Get AgentCore endpoint details from path
        proxy_path = event.get('pathParameters', {}).get('proxy', '')
        print(f"Proxy path (encoded): {proxy_path}")
        
        # URL decode the proxy path first
        decoded_proxy_path = urllib.parse.unquote(proxy_path)
        print(f"Proxy path (decoded): {decoded_proxy_path}")
        
        # Extract agent_arn from proxy path (format: agent_arn/invocations)
        original_agent_arn = decoded_proxy_path.replace('/invocations', '')
        print(f"Agent ARN from request: {original_agent_arn}")
        
        # Use the agent ARN from the request path
        # The UI/client is responsible for calling the correct agent based on tenant
        agent_arn = original_agent_arn
        
        session_id = event['headers'].get('X-Amzn-Bedrock-AgentCore-Runtime-Session-Id')
        bearer_token = event['headers'].get('Authorization', '').replace('Bearer ', '')
        
        print(f"Session ID: {session_id}")
        print(f"Bearer token present: {bool(bearer_token)}")
        
        # Parse the request body and add tenant info
        try:
            body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
        except json.JSONDecodeError:
            body = {}

        # Add tier, clinic_id, and user_id to the payload forwarded to AgentCore
        body['tier'] = tier
        body['clinic_id'] = clinic_id
        body['user_id'] = user_id
        print(f"Adding to payload - tier: {tier}, clinic_id: {clinic_id}, user_id: {user_id}")
        
        # Forward request to AgentCore
        response = forward_to_agentcore(
            agent_arn=agent_arn,
            payload=json.dumps(body),  # Send modified payload
            session_id=session_id,
            bearer_token=bearer_token,
            qualifier=event['queryStringParameters'].get('qualifier', 'DEFAULT')
        )
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'text/plain',
                'Access-Control-Allow-Origin': '*',
                'X-Tier': tier,
                'X-Clinic-ID': clinic_id,
                'X-User-ID': user_id
            },
            'body': response,
            'isBase64Encoded': False
        }
        
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

def extract_tenant_info(event: Dict[str, Any]) -> Dict[str, str]:
    """Extract tenant information from JWT token in Authorization header"""
    import jwt
    from jwt import PyJWKClient
    
    tenant_info = {
        'tier': 'basic',  # default tier
        'clinic_id': 'demo-clinic',  # default clinic
        'user_id': 'demo-user'  # default user
    }
    
    # Get Authorization header
    auth_header = event.get('headers', {}).get('Authorization', '')
    if not auth_header:
        print("Warning: No Authorization header found, using defaults")
        return tenant_info
    
    # Extract Bearer token
    bearer_token = auth_header.replace('Bearer ', '') if auth_header.startswith('Bearer ') else auth_header
    
    try:
        # Verify JWT token against Cognito JWKS
        user_pool_id = os.environ.get('COGNITO_USER_POOL_ID', '')
        client_id = os.environ.get('COGNITO_CLIENT_ID', '')
        
        if user_pool_id and client_id:
            region = user_pool_id.split('_')[0] if '_' in user_pool_id else os.environ.get('AWS_REGION', 'us-east-1')
            jwks_url = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}/.well-known/jwks.json"
            jwks_client = PyJWKClient(jwks_url, cache_keys=True)
            signing_key = jwks_client.get_signing_key_from_jwt(bearer_token)
            decoded = jwt.decode(
                bearer_token,
                signing_key.key,
                algorithms=["RS256"],
                audience=client_id,
                issuer=f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}",
            )
        else:
            print("Warning: COGNITO_USER_POOL_ID or COGNITO_CLIENT_ID not set, skipping JWT verification")
            decoded = jwt.decode(bearer_token, options={"verify_signature": False})  # nosemgrep: unverified-jwt-decode
        
        # Extract tier (basic/premium)
        if 'custom:tier' in decoded:
            tenant_info['tier'] = decoded['custom:tier']
        
        # Extract clinic_id from JWT custom attribute
        if 'custom:clinic_id' in decoded:
            tenant_info['clinic_id'] = decoded['custom:clinic_id']
        
        # Extract user_id from cognito:username or sub
        if 'cognito:username' in decoded:
            tenant_info['user_id'] = decoded['cognito:username']
        elif 'sub' in decoded:
            tenant_info['user_id'] = decoded['sub']
        
        print(f"Extracted from JWT - tier: {tenant_info['tier']}, clinic_id: {tenant_info['clinic_id']}, user_id: {tenant_info['user_id']}")
        
    except Exception as e:
        print(f"Warning: Could not decode JWT token: {e}, using defaults")
    
    # Fallback to headers if JWT decode failed
    if tenant_info['tier'] == 'basic' and 'X-Tier' in event.get('headers', {}):
        tenant_info['tier'] = event['headers']['X-Tier']
    
    return tenant_info

def forward_to_agentcore(agent_arn: str, payload: str, session_id: str, 
                        bearer_token: str, qualifier: str) -> str:
    """Forward request to AgentCore endpoint"""
    region = os.environ.get('AWS_REGION', 'us-east-1')
    escaped_arn = urllib.parse.quote(agent_arn, safe="")
    url = f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{escaped_arn}/invocations"
    
    print(f"Forwarding to URL: {url}")
    
    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "Content-Type": "application/json",
        "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": session_id,
    }
    
    try:
        body = json.loads(payload) if isinstance(payload, str) else payload
    except json.JSONDecodeError:
        body = {"payload": payload}
    
    print(f"Request body: {json.dumps(body)}")
    
    try:
        response = requests.post(
            url,
            params={"qualifier": qualifier},
            headers=headers,
            json=body,
            timeout=30,  # Reduced timeout
            stream=True,
        )
        
        print(f"Response status: {response.status_code}")
        print(f"Response headers: {dict(response.headers)}")
        
        response.raise_for_status()
        
        # Stream response back
        response_text = ""
        for line in response.iter_lines(chunk_size=1):
            if line:
                line = line.decode("utf-8")
                if line.startswith("data: "):
                    line = line[6:]
                    line = line.replace('"', "")
                    response_text += line
                elif line:
                    line = line.replace('"', "")
                    response_text += "\n" + line
        
        print(f"Response text length: {len(response_text)}")
        return response_text
        
    except requests.exceptions.Timeout:
        print("Request timed out")
        return "Request to AgentCore timed out"
    except requests.exceptions.RequestException as e:
        print(f"Request exception: {str(e)}")
        return f"Request error: {str(e)}"
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return f"Unexpected error: {str(e)}"
