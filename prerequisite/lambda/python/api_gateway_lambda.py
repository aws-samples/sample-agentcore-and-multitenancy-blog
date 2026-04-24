# Copyright 2026 Amazon.com and its affiliates; all rights reserved.
# SPDX-License-Identifier: MIT-0

"""
API Gateway Lambda proxy for AgentCore — tenant context extraction and throttling.

JWT signature verification is handled by AgentCore Runtime's Inbound JWT Authorizer
(configured via CustomJWTAuthorizerConfiguration). This Lambda only needs to:
  1. Decode the JWT (without signature verification) to extract tenant claims
  2. Enrich the payload with tenant context (tier, clinic_id, user_id)
  3. Forward the request with the original Bearer token to AgentCore Runtime

The AgentCore Runtime validates the token before the agent code ever runs.
"""

import json
import urllib.parse
import requests
import os
from typing import Dict, Any


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    API Gateway Lambda proxy to AgentCore with tenant-based throttling.
    JWT validation is delegated to AgentCore Runtime's Inbound JWT Authorizer.
    """
    try:
        print(f"Received event: {json.dumps(event)}")

        # Extract tenant claims from JWT (no signature verification needed —
        # AgentCore Runtime's Inbound JWT Authorizer handles that)
        tenant_info = extract_tenant_info(event)
        tier = tenant_info['tier']
        clinic_id = tenant_info['clinic_id']
        user_id = tenant_info['user_id']
        role = tenant_info['role']
        print(f"Tier: {tier}, Clinic ID: {clinic_id}, User ID: {user_id}, Role: {role}")

        # Get AgentCore endpoint details from path
        proxy_path = event.get('pathParameters', {}).get('proxy', '')
        decoded_proxy_path = urllib.parse.unquote(proxy_path)
        agent_arn = decoded_proxy_path.replace('/invocations', '')
        print(f"Agent ARN: {agent_arn}")

        session_id = event['headers'].get('X-Amzn-Bedrock-AgentCore-Runtime-Session-Id')
        bearer_token = event['headers'].get('Authorization', '').replace('Bearer ', '')

        # Parse the request body and enrich with tenant context
        try:
            body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
        except json.JSONDecodeError:
            body = {}

        body['tier'] = tier
        body['clinic_id'] = clinic_id
        body['user_id'] = user_id
        body['role'] = role

        # Forward to AgentCore Runtime (which validates the JWT via Inbound Authorizer)
        response = forward_to_agentcore(
            agent_arn=agent_arn,
            payload=json.dumps(body),
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
    """
    Extract tenant claims from JWT without signature verification.

    Signature verification is handled by AgentCore Runtime's Inbound JWT Authorizer.
    This function only decodes the token to read custom claims for tenant routing.
    """
    import jwt  # PyJWT

    tenant_info = {
        'tier': 'basic',
        'clinic_id': 'demo-clinic',
        'user_id': 'demo-user',
        'role': 'user',
    }

    auth_header = event.get('headers', {}).get('Authorization', '')
    if not auth_header:
        print("Warning: No Authorization header found, using defaults")
        return tenant_info

    bearer_token = auth_header.replace('Bearer ', '') if auth_header.startswith('Bearer ') else auth_header

    try:
        # Decode without verification — AgentCore Runtime validates the signature
        decoded = jwt.decode(bearer_token, options={"verify_signature": False})

        if 'custom:tier' in decoded:
            tenant_info['tier'] = decoded['custom:tier']

        if 'custom:clinic_id' in decoded:
            tenant_info['clinic_id'] = decoded['custom:clinic_id']

        if 'custom:role' in decoded:
            tenant_info['role'] = decoded['custom:role']

        if 'cognito:username' in decoded:
            tenant_info['user_id'] = decoded['cognito:username']
        elif 'sub' in decoded:
            tenant_info['user_id'] = decoded['sub']

        print(f"Extracted from JWT — tier: {tenant_info['tier']}, "
              f"clinic_id: {tenant_info['clinic_id']}, user_id: {tenant_info['user_id']}")

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
    
    print(f"Request body keys: {list(body.keys())}")
    
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
