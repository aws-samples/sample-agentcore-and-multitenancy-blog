#!/usr/bin/env python3
# Copyright 2026 Amazon.com and its affiliates; all rights reserved.
# SPDX-License-Identifier: MIT-0
#
# NOTICE: This script creates test users for demonstration purposes only.
# Do not use in production without proper security review.

"""
Create test users in Cognito with custom attributes for healthcare multi-tenancy demo.
This script is idempotent - it checks if users exist before creating them.
"""

import boto3
import sys
import json
from botocore.exceptions import ClientError

def get_ssm_parameter(parameter_name):
    """Retrieve parameter from SSM Parameter Store."""
    ssm = boto3.client('ssm')
    try:
        response = ssm.get_parameter(Name=parameter_name, WithDecryption=True)
        return response['Parameter']['Value']
    except ClientError as e:
        print(f"Error retrieving SSM parameter {parameter_name}: {e}")
        sys.exit(1)

def user_exists(cognito_client, user_pool_id, username):
    """Check if a user already exists in the user pool."""
    try:
        cognito_client.admin_get_user(
            UserPoolId=user_pool_id,
            Username=username
        )
        return True
    except cognito_client.exceptions.UserNotFoundException:
        return False
    except ClientError as e:
        print(f"Error checking if user exists: {e}")
        return False

def create_user(cognito_client, user_pool_id, user_data):
    """Create a single user with custom attributes."""
    username = user_data['username']
    
    # Check if user already exists (idempotent)
    if user_exists(cognito_client, user_pool_id, username):
        print(f"  ✓ User {username} already exists, skipping...")
        return True
    
    try:
        cognito_client.admin_create_user(
            UserPoolId=user_pool_id,
            Username=username,
            UserAttributes=[
                {'Name': 'email', 'Value': user_data['username']},
                {'Name': 'email_verified', 'Value': 'true'},
                {'Name': 'custom:tier', 'Value': user_data['tier']},
                {'Name': 'custom:clinic_id', 'Value': user_data['clinic_id']},
                {'Name': 'custom:role', 'Value': user_data['role']},
            ],
            TemporaryPassword=user_data['temp_password'],
            MessageAction='SUPPRESS'  # Don't send email for demo users
        )
        print(f"  ✓ Created user: {username}")
        return True
    except ClientError as e:
        print(f"  ✗ Error creating user {username}: {e}")
        return False

def main():
    print("🔐 Creating Healthcare Demo Test Users")
    print("=" * 60)
    
    # Get User Pool ID from SSM
    print("\n📋 Retrieving Cognito User Pool ID from SSM...")
    user_pool_id = get_ssm_parameter('/app/healthcare/agentcore/userpool_id')
    print(f"  User Pool ID: {user_pool_id}")
    
    cognito = boto3.client('cognito-idp')
    
    # Define test users based on clinic profiles
    basic_users = [
        {
            'username': 'dr.smith@clinic-a.com',
            'clinic_id': 'clinic-a',
            'tier': 'basic',
            'role': 'physician',
            'temp_password': 'TempPass123!',
            'name': 'Dr. Sarah Smith'
        },
        {
            'username': 'nurse.lee@clinic-a.com',
            'clinic_id': 'clinic-a',
            'tier': 'basic',
            'role': 'nurse',
            'temp_password': 'TempPass123!',
            'name': 'Nurse Jennifer Lee'
        },
        {
            'username': 'dr.chen@clinic-b.com',
            'clinic_id': 'clinic-b',
            'tier': 'basic',
            'role': 'physician',
            'temp_password': 'TempPass123!',
            'name': 'Dr. Michael Chen'
        },
        {
            'username': 'dr.rodriguez@clinic-c.com',
            'clinic_id': 'clinic-c',
            'tier': 'basic',
            'role': 'physician',
            'temp_password': 'TempPass123!',
            'name': 'Dr. Emily Rodriguez'
        },
    ]
    
    premium_users = [
        {
            'username': 'dr.foster@hospital-a.com',
            'clinic_id': 'hospital-a',
            'tier': 'premium',
            'role': 'physician',
            'temp_password': 'TempPass123!',
            'name': 'Dr. Amanda Foster'
        },
        {
            'username': 'dr.wilson@hospital-a.com',
            'clinic_id': 'hospital-a',
            'tier': 'premium',
            'role': 'physician',
            'temp_password': 'TempPass123!',
            'name': 'Dr. James Wilson'
        },
        {
            'username': 'dr.anderson@clinic-e.com',
            'clinic_id': 'clinic-e',
            'tier': 'premium',
            'role': 'physician',
            'temp_password': 'TempPass123!',
            'name': 'Dr. Thomas Anderson'
        },
        {
            'username': 'dr.green@clinic-f.com',
            'clinic_id': 'clinic-f',
            'tier': 'premium',
            'role': 'physician',
            'temp_password': 'TempPass123!',
            'name': 'Dr. Rachel Green'
        },
    ]
    
    all_users = basic_users + premium_users
    
    # Create users
    print(f"\n👥 Creating {len(basic_users)} Basic Tier users...")
    basic_success = 0
    for user in basic_users:
        if create_user(cognito, user_pool_id, user):
            basic_success += 1
    
    print(f"\n👥 Creating {len(premium_users)} Premium Tier users...")
    premium_success = 0
    for user in premium_users:
        if create_user(cognito, user_pool_id, user):
            premium_success += 1
    
    # Save credentials to file
    credentials_dir = 'credentials'
    import os
    os.makedirs(credentials_dir, exist_ok=True)
    
    credentials_file = f'{credentials_dir}/test_users.json'
    credentials_data = {
        'user_pool_id': user_pool_id,
        'basic_tier_users': basic_users,
        'premium_tier_users': premium_users,
        'note': 'All users have temporary password: TempPass123! - Users will be prompted to change on first login'
    }
    
    with open(credentials_file, 'w') as f:
        json.dump(credentials_data, f, indent=2)
    
    print(f"\n📄 Credentials saved to: {credentials_file}")
    
    # Summary
    print("\n" + "=" * 60)
    print("✅ User Creation Summary")
    print("=" * 60)
    print(f"  Basic Tier:   {basic_success}/{len(basic_users)} users created/verified")
    print(f"  Premium Tier: {premium_success}/{len(premium_users)} users created/verified")
    print(f"  Total:        {basic_success + premium_success}/{len(all_users)} users")
    print("\n📋 User Details:")
    print("  Temporary Password: TempPass123!")
    print("  Credentials File:   credentials/test_users.json")
    print("\n🔐 Custom Attributes Set:")
    print("  - custom:tier (tier: basic/premium)")
    print("  - custom:clinic_id (clinic identifier)")
    print("  - custom:role (physician/nurse/admin)")
    
    if basic_success + premium_success == len(all_users):
        print("\n✅ All users created/verified successfully!")
        return 0
    else:
        print(f"\n⚠️  Some users failed to create. Check errors above.")
        return 1

if __name__ == '__main__':
    sys.exit(main())
