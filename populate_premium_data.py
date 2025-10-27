#!/usr/bin/env python3
import boto3
import json
from decimal import Decimal

def populate_premium_data():
    """Populate premium DynamoDB tables with sample data"""
    
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    
    # Get table names
    client_table = dynamodb.Table('CustomerSupportStackInfra-ClientProfiles')
    portfolio_table = dynamodb.Table('CustomerSupportStackInfra-Portfolios')
    
    # Financial client data
    client_data = [
        {
            'client_id': 'CLIENT001',
            'name': 'Sarah Johnson',
            'risk_profile': 'Conservative',
            'assets_under_management': '2500000.00',
            'last_meeting': '2024-08-15',
            'advisor': 'Michael Chen'
        },
        {
            'client_id': 'CLIENT002', 
            'name': 'Robert Williams',
            'risk_profile': 'Aggressive',
            'assets_under_management': '5200000.00',
            'last_meeting': '2024-08-20',
            'advisor': 'Jennifer Davis'
        }
    ]
    
    # Portfolio data
    portfolio_data = [
        {
            'client_id': 'CLIENT001',
            'portfolio_id': 'PORT001',
            'portfolio_name': 'Conservative Growth',
            'current_value': '1500000.00',
            'ytd_return': '8.5%',
            'risk_level': 'Low'
        },
        {
            'client_id': 'CLIENT001',
            'portfolio_id': 'PORT002', 
            'portfolio_name': 'Bond Portfolio',
            'current_value': '1000000.00',
            'ytd_return': '4.2%',
            'risk_level': 'Very Low'
        },
        {
            'client_id': 'CLIENT002',
            'portfolio_id': 'PORT003',
            'portfolio_name': 'Growth Equity',
            'current_value': '3200000.00', 
            'ytd_return': '15.3%',
            'risk_level': 'High'
        },
        {
            'client_id': 'CLIENT002',
            'portfolio_id': 'PORT004',
            'portfolio_name': 'Tech Innovation',
            'current_value': '2000000.00',
            'ytd_return': '22.1%',
            'risk_level': 'Very High'
        }
    ]
    
    # Insert client data
    print("📊 Populating client profiles...")
    with client_table.batch_writer() as batch:
        for item in client_data:
            item = json.loads(json.dumps(item), parse_float=Decimal)
            batch.put_item(Item=item)
    
    # Insert portfolio data  
    print("💼 Populating portfolio data...")
    with portfolio_table.batch_writer() as batch:
        for item in portfolio_data:
            item = json.loads(json.dumps(item), parse_float=Decimal)
            batch.put_item(Item=item)
    
    print(f"✅ Successfully populated {len(client_data)} client profiles")
    print(f"✅ Successfully populated {len(portfolio_data)} portfolio records")

if __name__ == "__main__":
    populate_premium_data()
