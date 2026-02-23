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
        
        # Extract tenant info (tenant_id, clinic_id, and user_id) from JWT token or headers
        tenant_info = extract_tenant_info(event)
        tenant_id = tenant_info['tenant_id']
        clinic_id = tenant_info['clinic_id']
        user_id = tenant_info['user_id']
        print(f"Tenant ID: {tenant_id}, Clinic ID: {clinic_id}, User ID: {user_id}")
        
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

        # Add tenant_id, clinic_id, and user_id to the payload forwarded to AgentCore
        body['tenant_id'] = tenant_id
        body['clinic_id'] = clinic_id
        body['user_id'] = user_id
        print(f"Adding to payload - tenant_id: {tenant_id}, clinic_id: {clinic_id}, user_id: {user_id}")
        
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
                'X-Tenant-ID': tenant_id,
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
    
    tenant_info = {
        'tenant_id': 'basic',  # default tier
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
        # Decode JWT token without verification (already validated by AgentCore)
        decoded = jwt.decode(bearer_token, options={"verify_signature": False})
        
        # Extract tenant_id (tier: basic/premium)
        if 'custom:tenant_id' in decoded:
            tenant_info['tenant_id'] = decoded['custom:tenant_id']
        
        # Extract clinic_id from JWT custom attribute
        if 'custom:clinic_id' in decoded:
            tenant_info['clinic_id'] = decoded['custom:clinic_id']
        
        # Extract user_id from cognito:username or sub
        if 'cognito:username' in decoded:
            tenant_info['user_id'] = decoded['cognito:username']
        elif 'sub' in decoded:
            tenant_info['user_id'] = decoded['sub']
        
        print(f"Extracted from JWT - tenant_id: {tenant_info['tenant_id']}, clinic_id: {tenant_info['clinic_id']}, user_id: {tenant_info['user_id']}")
        
    except Exception as e:
        print(f"Warning: Could not decode JWT token: {e}, using defaults")
    
    # Fallback to headers if JWT decode failed
    if tenant_info['tenant_id'] == 'basic' and 'X-Tenant-ID' in event.get('headers', {}):
        tenant_info['tenant_id'] = event['headers']['X-Tenant-ID']
    
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
        
        if response.status_code != 200:
            error_text = response.text
            print(f"Error response: {error_text}")
            return f"AgentCore error: {response.status_code} - {error_text}"
        
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
