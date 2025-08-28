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
        
        # Extract tenant ID from JWT token or headers
        tenant_id = extract_tenant_id(event)
        print(f"Tenant ID: {tenant_id}")
        
        # Get AgentCore endpoint details
        proxy_path = event['pathParameters']['proxy']
        print(f"Proxy path (encoded): {proxy_path}")
        
        # URL decode the proxy path first
        decoded_proxy_path = urllib.parse.unquote(proxy_path)
        print(f"Proxy path (decoded): {decoded_proxy_path}")
        
        # Extract agent_arn from proxy path (format: agent_arn/invocations)
        agent_arn = decoded_proxy_path.replace('/invocations', '')
        print(f"Agent ARN: {agent_arn}")
        
        session_id = event['headers'].get('X-Amzn-Bedrock-AgentCore-Runtime-Session-Id')
        bearer_token = event['headers'].get('Authorization', '').replace('Bearer ', '')
        
        print(f"Session ID: {session_id}")
        print(f"Bearer token present: {bool(bearer_token)}")
        
        # Parse the request body and add tenant_id
        try:
            body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
        except json.JSONDecodeError:
            body = {}

        # Add tenant_id from headers to the payload
        tenant_id = event.get('headers', {}).get('X-Tenant-ID', 'basic')
        body['tenant_id'] = tenant_id  # Add tenant_id to payload
        print(f"Adding tenant_id to payload: {tenant_id}")
        
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
                'X-Tenant-ID': tenant_id
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

def extract_tenant_id(event: Dict[str, Any]) -> str:
    """Extract tenant ID from request"""
    # Option 1: From JWT claims
    request_context = event.get('requestContext', {})
    authorizer = request_context.get('authorizer', {})
    claims = authorizer.get('claims', {})
    
    if 'custom:tenant_id' in claims:
        return claims['custom:tenant_id']
    
    # Option 2: From headers
    return event['headers'].get('X-Tenant-ID', 'default')

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
