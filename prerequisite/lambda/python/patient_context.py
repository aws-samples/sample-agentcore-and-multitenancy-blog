"""
Patient Context Tool - Provides structured patient metadata lookup

This Lambda function retrieves patient-specific metadata from DynamoDB.
It helps the agent understand patient demographics, conditions, allergies, and visit history.

Data Source: Synthetic patient data generated from DESIGN/clinic-profiles.md
"""

import json
import boto3
import os
from typing import Dict, List, Optional
from datetime import datetime

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')
table_name = os.environ.get('PATIENT_METADATA_TABLE', 'healthcare-patient-metadata')
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
        'tier': headers.get('X-Tenant-ID') or body.get('tier', 'basic'),
        's3_prefix': headers.get('X-S3-Prefix') or body.get('s3_prefix', 'basic-tier/demo-clinic/')
    }


def lambda_handler(event, context):
    """
    Retrieve patient metadata with clinic isolation
    
    Parameters:
    - patient_id (optional): Specific patient to retrieve
    - list_patients (optional): If true, returns paginated list of patients for clinic
    - limit (optional): Number of patients to return in list (default: 20, max: 100)
    - last_evaluated_key (optional): Pagination token for next page
    
    Returns:
    - Single patient metadata object OR
    - List of patients with pagination info
    """
    try:
        # Extract tenant context
        tenant_info = extract_tenant_info(event)
        clinic_id = tenant_info['clinic_id']
        
        # Parse request parameters
        body = event.get('body', {})
        if isinstance(body, str):
            body = json.loads(body) if body else {}
        
        # Check if this is a list request
        if body.get('list_patients'):
            return handle_list_patients(clinic_id, body)
        
        # Single patient lookup
        patient_id = body.get('patient_id')
        if not patient_id:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'patient_id is required'})
            }
        
        # Retrieve patient metadata
        response = table.get_item(Key={'patient_id': patient_id})
        patient = response.get('Item')
        
        if not patient:
            return {
                'statusCode': 404,
                'body': json.dumps({'error': 'Patient not found'})
            }
        
        # Verify patient belongs to requesting clinic (application-level isolation)
        if patient.get('clinic_id') != clinic_id:
            return {
                'statusCode': 403,
                'body': json.dumps({'error': 'Access denied to this patient record'})
            }
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'patient': format_patient_metadata(patient)
            })
        }
    
    except Exception as e:
        print(f"Error in patient_context: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'Internal server error: {str(e)}'})
        }


def handle_list_patients(clinic_id: str, params: Dict) -> Dict:
    """Handle paginated list of patients for a clinic"""
    try:
        limit = min(int(params.get('limit', 20)), 100)
        
        # Query by clinic_id using GSI
        query_params = {
            'IndexName': 'clinic-index',
            'KeyConditionExpression': 'clinic_id = :clinic_id',
            'ExpressionAttributeValues': {':clinic_id': clinic_id},
            'Limit': limit
        }
        
        # Add pagination token if provided
        if params.get('last_evaluated_key'):
            query_params['ExclusiveStartKey'] = params['last_evaluated_key']
        
        response = table.query(**query_params)
        
        patients = [format_patient_metadata(p) for p in response.get('Items', [])]
        
        result = {
            'patients': patients,
            'count': len(patients)
        }
        
        # Include pagination token if more results available
        if 'LastEvaluatedKey' in response:
            result['last_evaluated_key'] = response['LastEvaluatedKey']
            result['has_more'] = True
        else:
            result['has_more'] = False
        
        return {
            'statusCode': 200,
            'body': json.dumps(result)
        }
    
    except Exception as e:
        print(f"Error listing patients: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'Error listing patients: {str(e)}'})
        }


def format_patient_metadata(patient: Dict) -> Dict:
    """Format patient metadata for response"""
    return {
        'patient_id': patient.get('patient_id'),
        'age': patient.get('age'),
        'gender': patient.get('gender'),
        'conditions': patient.get('conditions', []),
        'allergies': patient.get('allergies', []),
        'medications': patient.get('medications', []),
        'last_visit': patient.get('last_visit'),
        'last_visit_reason': patient.get('last_visit_reason'),
        'assigned_provider': patient.get('assigned_provider'),
        'clinic_id': patient.get('clinic_id'),
        'insurance_provider': patient.get('insurance_provider'),
        'emergency_contact': patient.get('emergency_contact')
    }
