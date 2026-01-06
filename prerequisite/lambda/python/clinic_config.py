"""
Clinic Configuration Tool - Provides clinic settings and capabilities

This Lambda function retrieves clinic-specific configuration from DynamoDB.
It helps the agent understand clinic context, specialties, services, and operating parameters.

Data Source: DESIGN/clinic-profiles.md
"""

import json
import boto3
import os
from typing import Dict

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
        'tier': headers.get('X-Tenant-ID') or body.get('tier', 'basic')
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
        # Extract tenant context
        tenant_info = extract_tenant_info(event)
        
        # Parse request parameters
        body = event.get('body', {})
        if isinstance(body, str):
            body = json.loads(body) if body else {}
        
        # Use clinic_id from request or default to tenant context
        clinic_id = body.get('clinic_id', tenant_info['clinic_id'])
        
        # Retrieve clinic configuration
        response = table.get_item(Key={'clinic_id': clinic_id})
        clinic_config = response.get('Item')
        
        if not clinic_config:
            return {
                'statusCode': 404,
                'body': json.dumps({'error': 'Clinic configuration not found'})
            }
        
        # Verify clinic belongs to requesting tier (optional security check)
        if clinic_config.get('tier') != tenant_info['tier']:
            return {
                'statusCode': 403,
                'body': json.dumps({'error': 'Access denied to this clinic configuration'})
            }
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'clinic': format_clinic_config(clinic_config)
            })
        }
    
    except Exception as e:
        print(f"Error in clinic_config: {str(e)}")
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
