# Copyright 2026 Amazon.com and its affiliates; all rights reserved.
# SPDX-License-Identifier: MIT-0

"""
Healthcare Multi-Tenant Lambda Function Handler

Routes tool requests to appropriate healthcare functions based on tenant tier.
Both basic and premium tiers have access to patient_context and clinic_config tools.

Tenant isolation is enforced through:
- X-Tenant-ID header (tier: basic/premium)
- X-Clinic-ID header (clinic identifier)
- X-S3-Prefix header (document scope)
"""

from patient_context import lambda_handler as patient_context_handler
from clinic_config import lambda_handler as clinic_config_handler


def get_named_parameter(event, name):
    """Extract parameter from event body"""
    if name not in event:
        return None
    return event.get(name)


def lambda_handler(event, context):
    """
    Main Lambda handler for healthcare tools
    
    Routes requests to:
    - patient_context: Patient metadata lookup with clinic isolation
    - clinic_config: Clinic configuration and capabilities
    """
    import json
    print(f"Event: {json.dumps(event, indent=2, default=str)}")
    print(f"Context: {context}")

    # Extract tool name from AgentCore context
    extended_tool_name = context.client_context.custom["bedrockAgentCoreToolName"]
    resource = extended_tool_name.split("___")[1]
    
    # Extract tenant context from propagated headers (AgentCore Gateway Lambda target)
    # For Lambda targets, headers arrive in context.client_context.custom['bedrockAgentCorePropagatedHeaders']
    propagated_headers = {}
    if hasattr(context, 'client_context') and context.client_context:
        propagated_headers = context.client_context.custom.get('bedrockAgentCorePropagatedHeaders', {})

    # Fallback to event headers (for direct invocation / testing)
    headers = propagated_headers if propagated_headers else event.get('headers', {})
    
    tenant_id = headers.get('X-Tenant-ID', headers.get('x-tenant-id', 'basic'))
    clinic_id = headers.get('X-Clinic-ID', headers.get('x-clinic-id', 'demo-clinic'))
    s3_prefix = headers.get('X-S3-Prefix', headers.get('x-s3-prefix', 'basic-tier/demo-clinic/'))
    
    print(f"🏥 Healthcare request - Tenant: {tenant_id}, Clinic: {clinic_id}, Tool: {resource}")
    print(f"📋 Headers received: {list(headers.keys())}")
    
    # Inject resolved headers into event so downstream handlers can read them
    # via their existing extract_tenant_info() which reads event['headers']
    event['headers'] = headers
    
    # Route to healthcare tools (available to both basic and premium tiers)
    if resource == "patient_context":
        print(f"calling patient context tool")
        return patient_context_handler(event, context)
    
    elif resource == "clinic_config":
        return clinic_config_handler(event, context)
    
    # Unknown tool
    return {
        "statusCode": 404,
        "body": f"❌ Tool '{resource}' not found. Available tools: patient_context, clinic_config",
    }
