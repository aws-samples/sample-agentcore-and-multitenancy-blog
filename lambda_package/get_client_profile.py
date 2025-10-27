import boto3
import json
from boto3.dynamodb.conditions import Key

# Initialize DynamoDB resource
dynamodb = boto3.resource("dynamodb")

def get_client_profile(client_id):
    """Get financial client profile and information"""
    
    # Get table name from environment variable
    import os
    table_name = os.environ.get('CLIENT_PROFILE_TABLE')
    
    if not table_name:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Client profile table not configured"})
        }
    
    table = dynamodb.Table(table_name)
    
    try:
        # Query the table for the client
        response = table.get_item(
            Key={
                'client_id': client_id
            }
        )
        
        if 'Item' in response:
            client = response['Item']
            return {
                "statusCode": 200,
                "body": json.dumps({
                    "client_id": client['client_id'],
                    "name": client['name'],
                    "risk_profile": client['risk_profile'],
                    "assets_under_management": client['assets_under_management'],
                    "last_meeting": client.get('last_meeting', 'No recent meetings'),
                    "advisor": client.get('advisor', 'Not assigned')
                })
            }
        else:
            return {
                "statusCode": 404,
                "body": json.dumps({"error": f"Client {client_id} not found"})
            }
            
    except Exception as e:
        print(f"Error retrieving client profile: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": f"Database error: {str(e)}"})
        }
