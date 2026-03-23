# Copyright 2026 Amazon.com and its affiliates; all rights reserved.
# SPDX-License-Identifier: MIT-0

"""
Clinic Configuration Tool - Provides clinic settings and capabilities

This Lambda function retrieves clinic-specific configuration from DynamoDB.
It helps the agent understand clinic context, specialties, services, and operating parameters.

Data Source: DESIGN/clinic-profiles.md
"""

import json
import boto3
import os
from decimal import Decimal
from typing import Dict


def decimal_default(obj):
    """JSON serializer for DynamoDB Decimal types"""
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')
table_name = os.environ.get('CLINIC_CONFIG_TABLE', 'healthcare-clinic-config')
table = dynamodb.Table(table_name)


def extract_tenant_info(event: Dict) -> Dict:
    """Extract tenant information from request headers or body"""
    headers = event.get('headers', {})
    body = event.get('body', {})
    
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except:
            body = {}
    
    return {
        'clinic_id': headers.get('X-Clinic-ID') or body.get('clinic_id', 'demo-clinic'),
        'tier': headers.get('X-Tier') or body.get('tier', 'basic')
    }


def lambda_handler(event, context):
    """
    Retrieve clinic configuration
    
    Parameters:
    - clinic_id (optional): Specific clinic to retrieve (defaults to tenant context)
    
    Returns:
    - Clinic configuration object with specialty, services, hours, providers
    """
    try:
        print(f"📋 [clinic_config] Received event: {json.dumps(event, indent=2, default=str)}")
        
        # Extract tenant context
        tenant_info = extract_tenant_info(event)
        print(f"🏥 [clinic_config] Tenant info: {json.dumps(tenant_info)}")
        
        # Parse request parameters - check top-level event keys first (AgentCore sends params as top-level keys)
        clinic_id = event.get('clinic_id')
        
        # Fallback to body if not found at top level
        body = event.get('body', {})
        if isinstance(body, str):
            body = json.loads(body) if body else {}
        
        if clinic_id is None:
            clinic_id = body.get('clinic_id')
        
        # Default to tenant context clinic
        if clinic_id is None:
            clinic_id = tenant_info['clinic_id']
        
        print(f"🔍 [clinic_config] Looking up clinic: {clinic_id} in table: {table_name}")
        
        # Retrieve clinic configuration
        response = table.get_item(Key={'clinic_id': clinic_id})
        clinic_config = response.get('Item')
        
        if not clinic_config:
            print(f"❌ [clinic_config] Clinic {clinic_id} not found")
            return {
                'statusCode': 404,
                'body': json.dumps({'error': 'Clinic configuration not found'})
            }
        
        print(f"✅ [clinic_config] Found clinic {clinic_id}, tier: {clinic_config.get('tier')}")
        
        # Verify clinic belongs to requesting tier (optional security check)
        if clinic_config.get('tier') != tenant_info['tier']:
            print(f"🚫 [clinic_config] Tier mismatch - clinic tier: {clinic_config.get('tier')}, requesting tier: {tenant_info['tier']}")
            return {
                'statusCode': 403,
                'body': json.dumps({'error': 'Access denied to this clinic configuration'})
            }
        
        result = {
            'statusCode': 200,
            'body': json.dumps({
                'clinic': format_clinic_config(clinic_config)
            }, default=decimal_default)
        }
        print(f"✅ [clinic_config] Returning config for {clinic_id}")
        return result
    
    except Exception as e:
        print(f"❌ [clinic_config] Error: {str(e)}")
        import traceback
        print(f"❌ [clinic_config] Traceback: {traceback.format_exc()}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'Internal server error: {str(e)}'})
        }


def format_clinic_config(config: Dict) -> Dict:
    """Format clinic configuration for response"""
    return {
        'clinic_id': config.get('clinic_id'),
        'clinic_name': config.get('clinic_name'),
        'specialty': config.get('specialty'),
        'tier': config.get('tier'),
        'location': config.get('location'),
        'patient_volume': config.get('patient_volume'),
        'available_services': config.get('available_services', []),
        'operating_hours': config.get('operating_hours'),
        'providers': config.get('providers', []),
        's3_prefix': config.get('s3_prefix')
    }
