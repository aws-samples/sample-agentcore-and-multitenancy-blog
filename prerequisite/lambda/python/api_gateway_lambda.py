# Copyright 2026 Amazon.com and its affiliates; all rights reserved.
# SPDX-License-Identifier: MIT-0

"""
API Gateway Lambda proxy for AgentCore — tenant context extraction and throttling.

JWT signature verification is handled by AgentCore Runtime's Inbound JWT Authorizer
(configured via CustomJWTAuthorizerConfiguration). This Lambda only needs to:
  1. Decode the JWT (without signature verification) to extract tenant claims
  2. Enrich the payload with tenant context (tier, clinic_id, user_id)
  3. Forward the request with the original Bearer token to AgentCore Runtime

Uses the boto3 bedrock-agentcore SDK with bearer token injection via botocore
event hooks, following the pattern from:
  https://github.com/awslabs/agentcore-samples/blob/main/01-tutorials/03-AgentCore-identity/10-runtime-inbound-outbound-auth/invoke.py
"""

import json
import urllib.parse
import boto3
import os
from typing import Dict, Any

# Initialize outside handler for connection reuse across Lambda invocations
agentcore_client = boto3.client(
    'bedrock-agentcore',
    region_name=os.environ.get('AWS_REGION', 'us-east-1')
)


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
            user_id=user_id,
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
                         bearer_token: str, user_id: str, qualifier: str) -> str:
    """
    Forward request to AgentCore Runtime using boto3 SDK.

    Uses botocore event hooks to inject the Bearer token alongside SigV4 auth,
    so AgentCore's Inbound JWT Authorizer can still validate the user's JWT.
    Pattern from: awslabs/agentcore-samples (10-runtime-inbound-outbound-auth/invoke.py)
    """
    print(f"Invoking AgentCore SDK — ARN: {agent_arn}, qualifier: {qualifier}")

    # Register event handler to inject Bearer token into the request.
    # boto3 doesn't have a native bearerToken param, so we use the botocore
    # event system to add the Authorization header before the request is sent.
    def _inject_bearer(request, **kwargs):
        request.headers["Authorization"] = f"Bearer {bearer_token}"

    agentcore_client.meta.events.register(
        "before-send.bedrock-agentcore.InvokeAgentRuntime", _inject_bearer
    )

    try:
        response = agentcore_client.invoke_agent_runtime(
            agentRuntimeArn=agent_arn,
            runtimeSessionId=session_id,
            runtimeUserId=user_id,
            qualifier=qualifier,
            payload=payload.encode('utf-8') if isinstance(payload, str) else payload,
        )

        print(f"Response status: {response.get('statusCode')}, "
              f"content-type: {response.get('contentType', '')}")

        return _parse_streaming_response(response)

    except agentcore_client.exceptions.ThrottlingException:
        print("Throttled by AgentCore")
        return "Service is busy, please try again"
    except agentcore_client.exceptions.ResourceNotFoundException:
        print(f"Agent not found: {agent_arn}")
        return f"Agent not found: {agent_arn}"
    except agentcore_client.exceptions.AccessDeniedException as e:
        print(f"Access denied: {e}")
        return "Access denied to agent runtime"
    except agentcore_client.exceptions.ValidationException as e:
        print(f"Validation error: {e}")
        return f"Validation error: {str(e)}"
    except Exception as e:
        print(f"SDK error: {type(e).__name__}: {e}")
        return f"Error: {str(e)}"
    finally:
        # Always unregister to avoid leaking the handler to subsequent invocations
        agentcore_client.meta.events.unregister(
            "before-send.bedrock-agentcore.InvokeAgentRuntime", _inject_bearer
        )


def _parse_streaming_response(response: dict) -> str:
    """Parse the streaming response from AgentCore SDK."""
    content_type = response.get('contentType', '')

    # Handle SSE streaming response
    if 'text/event-stream' in content_type:
        response_text = ""
        for line in response['response'].iter_lines(chunk_size=10):
            if line:
                line = line.decode('utf-8')
                if line.startswith('data: '):
                    line = line[6:].replace('"', '')
                    response_text += line
                elif line:
                    response_text += "\n" + line.replace('"', '')
        print(f"Response text length: {len(response_text)}")
        return response_text

    # Handle JSON response
    elif content_type == 'application/json':
        chunks = []
        for chunk in response.get('response', []):
            if isinstance(chunk, bytes):
                chunks.append(chunk.decode('utf-8'))
            elif isinstance(chunk, dict):
                raw = chunk.get('chunk', {}).get('bytes', b'')
                if raw:
                    chunks.append(raw.decode('utf-8'))
        return ''.join(chunks)

    # Fallback: read raw StreamingBody
    else:
        raw = response['response'].read().decode('utf-8')
        print(f"Raw response length: {len(raw)}")
        return raw
