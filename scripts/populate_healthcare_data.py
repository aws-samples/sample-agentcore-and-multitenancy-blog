#!/usr/bin/env python3
"""
Healthcare Data Population Script

Populates DynamoDB tables with synthetic patient metadata and clinic configurations
based on clinic profiles defined in DESIGN/clinic-profiles.md

This script is idempotent - it checks if data exists before populating.
"""

import boto3
import json
import sys
from datetime import datetime, timedelta
import random
from decimal import Decimal

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
ssm = boto3.client('ssm')


def get_table_name(ssm_path: str) -> str:
    """Retrieve table name from SSM parameter"""
    try:
        response = ssm.get_parameter(Name=ssm_path)
        return response['Parameter']['Value']
    except Exception as e:
        print(f"Error retrieving SSM parameter {ssm_path}: {e}")
        raise


def table_has_data(table_name: str) -> bool:
    """Check if table already has data"""
    try:
        table = dynamodb.Table(table_name)
        response = table.scan(Limit=1)
        return response['Count'] > 0
    except Exception as e:
        print(f"Error checking table {table_name}: {e}")
        return False


def populate_patient_metadata():
    """Populate patient metadata table with synthetic data"""
    print("\n=== Populating Patient Metadata ===")
    
    # Get table name from SSM
    table_name = get_table_name('/app/healthcare/dynamodb/patient_metadata_table_name')
    print(f"Table: {table_name}")
    
    # Check if data already exists
    if table_has_data(table_name):
        print("✓ Patient metadata already populated, skipping")
        return
    
    table = dynamodb.Table(table_name)
    
    # Define patient data based on clinic profiles
    # NOTE: All assigned_provider values match Cognito users created in create_test_users.py
    # Basic Tier Clinics
    patients = [
        # Clinic A: Family Practice (4 patients)
        # Providers: Dr. Sarah Smith (Cognito user), Nurse Jennifer Lee (Cognito user)
        {
            'patient_id': 'P10001',
            'clinic_id': 'clinic-a',
            'age': 45,
            'gender': 'Female',
            'conditions': ['hypertension', 'type-2-diabetes'],
            'allergies': ['penicillin'],
            'medications': ['metformin', 'lisinopril'],
            'last_visit': '2024-12-15',
            'last_visit_reason': 'Annual physical exam',
            'assigned_provider': 'Dr. Sarah Smith',
            'insurance_provider': 'Blue Cross',
            'emergency_contact': 'John Doe (555-0101)'
        },
        {
            'patient_id': 'P10002',
            'clinic_id': 'clinic-a',
            'age': 32,
            'gender': 'Male',
            'conditions': ['asthma'],
            'allergies': [],
            'medications': ['albuterol inhaler'],
            'last_visit': '2024-12-20',
            'last_visit_reason': 'Asthma follow-up',
            'assigned_provider': 'Nurse Jennifer Lee',
            'insurance_provider': 'Aetna',
            'emergency_contact': 'Jane Smith (555-0102)'
        },
        {
            'patient_id': 'P10003',
            'clinic_id': 'clinic-a',
            'age': 67,
            'gender': 'Male',
            'conditions': ['hypertension', 'high-cholesterol', 'arthritis'],
            'allergies': ['sulfa drugs'],
            'medications': ['atorvastatin', 'amlodipine', 'ibuprofen'],
            'last_visit': '2024-12-10',
            'last_visit_reason': 'Chronic disease management',
            'assigned_provider': 'Dr. Sarah Smith',
            'insurance_provider': 'Medicare',
            'emergency_contact': 'Mary Johnson (555-0103)'
        },
        {
            'patient_id': 'P10004',
            'clinic_id': 'clinic-a',
            'age': 29,
            'gender': 'Female',
            'conditions': ['anxiety', 'hypothyroidism'],
            'allergies': [],
            'medications': ['levothyroxine', 'sertraline'],
            'last_visit': '2025-01-08',
            'last_visit_reason': 'Medication review',
            'assigned_provider': 'Nurse Jennifer Lee',
            'insurance_provider': 'Blue Shield',
            'emergency_contact': 'Spouse (555-0104)'
        },
        
        # Clinic B: Urgent Care (3 patients)
        # Provider: Dr. Michael Chen (Cognito user)
        {
            'patient_id': 'P20001',
            'clinic_id': 'clinic-b',
            'age': 28,
            'gender': 'Female',
            'conditions': [],
            'allergies': [],
            'medications': [],
            'last_visit': '2025-01-05',
            'last_visit_reason': 'Ankle sprain',
            'assigned_provider': 'Dr. Michael Chen',
            'insurance_provider': 'United Healthcare',
            'emergency_contact': 'Tom Martinez (555-0201)'
        },
        {
            'patient_id': 'P20002',
            'clinic_id': 'clinic-b',
            'age': 42,
            'gender': 'Male',
            'conditions': ['seasonal-allergies'],
            'allergies': [],
            'medications': ['cetirizine'],
            'last_visit': '2025-01-04',
            'last_visit_reason': 'Laceration repair',
            'assigned_provider': 'Dr. Michael Chen',
            'insurance_provider': 'Cigna',
            'emergency_contact': 'Lisa Chen (555-0202)'
        },
        {
            'patient_id': 'P20003',
            'clinic_id': 'clinic-b',
            'age': 19,
            'gender': 'Female',
            'conditions': [],
            'allergies': [],
            'medications': [],
            'last_visit': '2025-01-06',
            'last_visit_reason': 'Flu symptoms',
            'assigned_provider': 'Dr. Michael Chen',
            'insurance_provider': 'Blue Shield',
            'emergency_contact': 'Parent (555-0203)'
        },
        
        # Clinic C: Pediatrics (3 patients)
        # Provider: Dr. Emily Rodriguez (Cognito user)
        {
            'patient_id': 'P30001',
            'clinic_id': 'clinic-c',
            'age': 5,
            'gender': 'Male',
            'conditions': [],
            'allergies': ['peanuts'],
            'medications': [],
            'last_visit': '2024-12-18',
            'last_visit_reason': 'Well-child visit',
            'assigned_provider': 'Dr. Emily Rodriguez',
            'insurance_provider': 'Blue Cross',
            'emergency_contact': 'Parents (555-0301)'
        },
        {
            'patient_id': 'P30002',
            'clinic_id': 'clinic-c',
            'age': 2,
            'gender': 'Female',
            'conditions': [],
            'allergies': [],
            'medications': [],
            'last_visit': '2024-12-22',
            'last_visit_reason': 'Vaccination',
            'assigned_provider': 'Dr. Emily Rodriguez',
            'insurance_provider': 'Aetna',
            'emergency_contact': 'Parents (555-0302)'
        },
        {
            'patient_id': 'P30003',
            'clinic_id': 'clinic-c',
            'age': 8,
            'gender': 'Female',
            'conditions': ['asthma'],
            'allergies': [],
            'medications': ['albuterol inhaler'],
            'last_visit': '2025-01-03',
            'last_visit_reason': 'Ear infection',
            'assigned_provider': 'Dr. Emily Rodriguez',
            'insurance_provider': 'United Healthcare',
            'emergency_contact': 'Parents (555-0303)'
        },
        
        # Clinic D: Internal Medicine (0 patients)
        # NOTE: No Cognito users exist for this clinic, so no patients assigned
        # This clinic can be used for future expansion
        
        # Premium Tier Clinics
        # Hospital A: Multi-Specialty (4 patients)
        # Providers: Dr. Amanda Foster (Cognito user), Dr. James Wilson (Cognito user)
        {
            'patient_id': 'P50001',
            'clinic_id': 'hospital-a',
            'age': 62,
            'gender': 'Male',
            'conditions': ['coronary-artery-disease', 'hypertension', 'high-cholesterol'],
            'allergies': [],
            'medications': ['aspirin', 'clopidogrel', 'atorvastatin', 'metoprolol'],
            'last_visit': '2024-12-28',
            'last_visit_reason': 'Cardiac catheterization follow-up',
            'assigned_provider': 'Dr. Amanda Foster',
            'insurance_provider': 'Blue Cross PPO',
            'emergency_contact': 'Spouse (555-0501)'
        },
        {
            'patient_id': 'P50002',
            'clinic_id': 'hospital-a',
            'age': 55,
            'gender': 'Female',
            'conditions': ['breast-cancer-stage-2', 'hypertension'],
            'allergies': ['latex'],
            'medications': ['tamoxifen', 'lisinopril'],
            'last_visit': '2025-01-04',
            'last_visit_reason': 'Oncology consultation',
            'assigned_provider': 'Dr. James Wilson',
            'insurance_provider': 'Aetna PPO',
            'emergency_contact': 'Daughter (555-0502)'
        },
        {
            'patient_id': 'P50003',
            'clinic_id': 'hospital-a',
            'age': 48,
            'gender': 'Male',
            'conditions': ['atrial-fibrillation', 'heart-failure'],
            'allergies': [],
            'medications': ['warfarin', 'carvedilol', 'furosemide'],
            'last_visit': '2024-12-30',
            'last_visit_reason': 'Echocardiogram',
            'assigned_provider': 'Dr. Amanda Foster',
            'insurance_provider': 'United Healthcare PPO',
            'emergency_contact': 'Spouse (555-0503)'
        },
        {
            'patient_id': 'P50004',
            'clinic_id': 'hospital-a',
            'age': 67,
            'gender': 'Female',
            'conditions': ['lung-cancer-stage-3', 'COPD'],
            'allergies': ['morphine'],
            'medications': ['chemotherapy-regimen', 'tiotropium', 'prednisone'],
            'last_visit': '2025-01-02',
            'last_visit_reason': 'Chemotherapy session',
            'assigned_provider': 'Dr. James Wilson',
            'insurance_provider': 'Medicare Advantage',
            'emergency_contact': 'Son (555-0504)'
        },
        
        # Clinic E: Cardiology (3 patients)
        # Provider: Dr. Thomas Anderson (Cognito user)
        {
            'patient_id': 'P60001',
            'clinic_id': 'clinic-e',
            'age': 59,
            'gender': 'Male',
            'conditions': ['heart-failure', 'hypertension', 'type-2-diabetes'],
            'allergies': [],
            'medications': ['carvedilol', 'lisinopril', 'furosemide', 'metformin'],
            'last_visit': '2024-12-27',
            'last_visit_reason': 'Heart failure management',
            'assigned_provider': 'Dr. Thomas Anderson',
            'insurance_provider': 'Blue Cross PPO',
            'emergency_contact': 'Spouse (555-0601)'
        },
        {
            'patient_id': 'P60002',
            'clinic_id': 'clinic-e',
            'age': 71,
            'gender': 'Female',
            'conditions': ['coronary-artery-disease', 'hypertension'],
            'allergies': ['aspirin'],
            'medications': ['clopidogrel', 'atorvastatin', 'amlodipine'],
            'last_visit': '2025-01-03',
            'last_visit_reason': 'Post-stent follow-up',
            'assigned_provider': 'Dr. Thomas Anderson',
            'insurance_provider': 'Medicare Advantage',
            'emergency_contact': 'Daughter (555-0602)'
        },
        {
            'patient_id': 'P60003',
            'clinic_id': 'clinic-e',
            'age': 54,
            'gender': 'Male',
            'conditions': ['atrial-fibrillation', 'hypertension'],
            'allergies': [],
            'medications': ['apixaban', 'metoprolol', 'losartan'],
            'last_visit': '2024-12-29',
            'last_visit_reason': 'Holter monitor review',
            'assigned_provider': 'Dr. Thomas Anderson',
            'insurance_provider': 'Aetna PPO',
            'emergency_contact': 'Spouse (555-0603)'
        },
        
        # Clinic F: Oncology (3 patients)
        # Provider: Dr. Rachel Green (Cognito user)
        {
            'patient_id': 'P70001',
            'clinic_id': 'clinic-f',
            'age': 52,
            'gender': 'Female',
            'conditions': ['breast-cancer-HER2-positive', 'hypertension'],
            'allergies': [],
            'medications': ['trastuzumab', 'pertuzumab', 'lisinopril'],
            'last_visit': '2025-01-05',
            'last_visit_reason': 'Immunotherapy infusion',
            'assigned_provider': 'Dr. Rachel Green',
            'insurance_provider': 'Blue Cross PPO',
            'emergency_contact': 'Spouse (555-0701)'
        },
        {
            'patient_id': 'P70002',
            'clinic_id': 'clinic-f',
            'age': 64,
            'gender': 'Male',
            'conditions': ['lung-cancer-stage-4', 'COPD'],
            'allergies': ['contrast-dye'],
            'medications': ['pembrolizumab', 'tiotropium'],
            'last_visit': '2025-01-04',
            'last_visit_reason': 'PET scan review',
            'assigned_provider': 'Dr. Rachel Green',
            'insurance_provider': 'Medicare Advantage',
            'emergency_contact': 'Daughter (555-0702)'
        },
        {
            'patient_id': 'P70003',
            'clinic_id': 'clinic-f',
            'age': 47,
            'gender': 'Male',
            'conditions': ['prostate-cancer-stage-2'],
            'allergies': [],
            'medications': ['bicalutamide', 'leuprolide'],
            'last_visit': '2024-12-30',
            'last_visit_reason': 'Radiation planning',
            'assigned_provider': 'Dr. Rachel Green',
            'insurance_provider': 'United Healthcare PPO',
            'emergency_contact': 'Spouse (555-0703)'
        },
        
        # Hospital B: Academic Medical Center (0 patients)
        # NOTE: No Cognito users exist for this hospital, so no patients assigned
        # This hospital can be used for future expansion
    ]
    
    # Convert to DynamoDB format
    for patient in patients:
        patient = json.loads(json.dumps(patient), parse_float=Decimal)
    
    # Batch write to DynamoDB
    print(f"Inserting {len(patients)} patient records...")
    with table.batch_writer() as batch:
        for patient in patients:
            batch.put_item(Item=patient)
    
    print(f"✓ Successfully populated {len(patients)} patient records")


def populate_clinic_config():
    """Populate clinic configuration table with data from clinic profiles"""
    print("\n=== Populating Clinic Configuration ===")
    
    # Get table name from SSM
    table_name = get_table_name('/app/healthcare/dynamodb/clinic_config_table_name')
    print(f"Table: {table_name}")
    
    # Check if data already exists
    if table_has_data(table_name):
        print("✓ Clinic configuration already populated, skipping")
        return
    
    table = dynamodb.Table(table_name)
    
    # Define clinic configurations based on DESIGN/clinic-profiles.md
    clinics = [
        # Basic Tier
        # NOTE: Only providers with Cognito accounts are listed
        {
            'clinic_id': 'clinic-a',
            'clinic_name': 'Family Practice Medical Center',
            'specialty': 'Family Medicine / Primary Care',
            'tier': 'basic',
            'location': 'Suburban community',
            'patient_volume': '~50 patients/day',
            'available_services': [
                'patient-intake',
                'appointment-notes',
                'lab-results',
                'prescriptions',
                'vital-signs'
            ],
            'operating_hours': '8am-5pm',
            'providers': ['Dr. Sarah Smith', 'Nurse Jennifer Lee'],
            's3_prefix': 'basic-tier/clinic-a/'
        },
        {
            'clinic_id': 'clinic-b',
            'clinic_name': 'QuickCare Urgent Care',
            'specialty': 'Urgent Care / Walk-in Clinic',
            'tier': 'basic',
            'location': 'Urban shopping district',
            'patient_volume': '~80 patients/day',
            'available_services': [
                'patient-intake',
                'injury-reports',
                'diagnostic-notes',
                'lab-results',
                'discharge-instructions'
            ],
            'operating_hours': '10am-9pm',
            'providers': ['Dr. Michael Chen'],
            's3_prefix': 'basic-tier/clinic-b/'
        },
        {
            'clinic_id': 'clinic-c',
            'clinic_name': 'Bright Beginnings Pediatrics',
            'specialty': 'Pediatrics',
            'tier': 'basic',
            'location': 'Family-oriented suburb',
            'patient_volume': '~40 patients/day',
            'available_services': [
                'well-child-visits',
                'vaccination-records',
                'sick-visit-notes',
                'growth-charts',
                'parent-education'
            ],
            'operating_hours': '9am-5pm',
            'providers': ['Dr. Emily Rodriguez'],
            's3_prefix': 'basic-tier/clinic-c/'
        },
        {
            'clinic_id': 'clinic-d',
            'clinic_name': 'Wellness Internal Medicine',
            'specialty': 'Internal Medicine',
            'tier': 'basic',
            'location': 'Medical office building',
            'patient_volume': '~35 patients/day',
            'available_services': [
                'chronic-disease-management',
                'annual-physicals',
                'lab-results',
                'medication-management',
                'specialist-referrals'
            ],
            'operating_hours': '8am-12pm',
            'providers': [],
            's3_prefix': 'basic-tier/clinic-d/'
        },
        
        # Premium Tier
        # NOTE: Only providers with Cognito accounts are listed
        {
            'clinic_id': 'hospital-a',
            'clinic_name': 'Metropolitan Multi-Specialty Medical Center',
            'specialty': 'Multi-Specialty Hospital (Cardiology, Oncology, Surgery)',
            'tier': 'premium',
            'location': 'Urban academic medical center',
            'patient_volume': '~200 patients/day',
            'available_services': [
                'diagnostic-reports',
                'imaging-studies',
                'pathology-reports',
                'surgical-notes',
                'specialist-consultations',
                'research-data'
            ],
            'operating_hours': '7am-6pm',
            'providers': ['Dr. Amanda Foster', 'Dr. James Wilson'],
            's3_prefix': 'premium-tier/hospital-a/'
        },
        {
            'clinic_id': 'clinic-e',
            'clinic_name': 'Advanced Cardiology Associates',
            'specialty': 'Cardiology',
            'tier': 'premium',
            'location': 'Specialty medical campus',
            'patient_volume': '~60 patients/day',
            'available_services': [
                'cardiac-catheterization',
                'echocardiogram',
                'stress-tests',
                'holter-monitoring',
                'cardiac-imaging',
                'heart-failure-management'
            ],
            'operating_hours': '7am-5pm',
            'providers': ['Dr. Thomas Anderson'],
            's3_prefix': 'premium-tier/clinic-e/'
        },
        {
            'clinic_id': 'clinic-f',
            'clinic_name': 'Comprehensive Cancer Care Center',
            'specialty': 'Oncology',
            'tier': 'premium',
            'location': 'Cancer treatment center',
            'patient_volume': '~50 patients/day',
            'available_services': [
                'pathology-reports',
                'imaging-studies',
                'treatment-plans',
                'clinical-trials',
                'tumor-board',
                'genomic-testing'
            ],
            'operating_hours': '8am-5pm',
            'providers': ['Dr. Rachel Green'],
            's3_prefix': 'premium-tier/clinic-f/'
        },
        {
            'clinic_id': 'hospital-b',
            'clinic_name': 'University Academic Medical Center',
            'specialty': 'Academic Medical Center (Teaching Hospital)',
            'tier': 'premium',
            'location': 'University campus',
            'patient_volume': '~250 patients/day',
            'available_services': [
                'admission-notes',
                'progress-notes',
                'procedure-notes',
                'discharge-summaries',
                'teaching-cases',
                'research-data',
                'imaging-studies',
                'pathology-reports'
            ],
            'operating_hours': '6am-8pm',
            'providers': [],
            's3_prefix': 'premium-tier/hospital-b/'
        }
    ]
    
    # Convert to DynamoDB format
    for clinic in clinics:
        clinic = json.loads(json.dumps(clinic), parse_float=Decimal)
    
    # Batch write to DynamoDB
    print(f"Inserting {len(clinics)} clinic configurations...")
    with table.batch_writer() as batch:
        for clinic in clinics:
            batch.put_item(Item=clinic)
    
    print(f"✓ Successfully populated {len(clinics)} clinic configurations")


def main():
    """Main execution function"""
    print("=" * 60)
    print("Healthcare Data Population Script")
    print("=" * 60)
    
    try:
        # Populate patient metadata
        populate_patient_metadata()
        
        # Populate clinic configurations
        populate_clinic_config()
        
        print("\n" + "=" * 60)
        print("✓ Healthcare data population completed successfully!")
        print("=" * 60)
        return 0
        
    except Exception as e:
        print(f"\n✗ Error during data population: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
