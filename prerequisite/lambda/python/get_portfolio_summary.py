import boto3
import json
from boto3.dynamodb.conditions import Key

# Initialize DynamoDB resource
dynamodb = boto3.resource("dynamodb")

def get_portfolio_summary(client_id):
    """Get client portfolio performance and holdings summary"""
    
    # Get table name from environment variable
    import os
    table_name = os.environ.get('PORTFOLIO_TABLE')
    
    if not table_name:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Portfolio table not configured"})
        }
    
    table = dynamodb.Table(table_name)
    
    try:
        # Query all portfolios for the client
        response = table.query(
            KeyConditionExpression=Key('client_id').eq(client_id)
        )
        
        if response['Items']:
            portfolios = response['Items']
            
            # Calculate total value and performance
            total_value = sum(float(portfolio['current_value']) for portfolio in portfolios)
            
            # Format portfolio summary
            portfolio_summary = []
            for portfolio in portfolios:
                portfolio_summary.append({
                    "portfolio_id": portfolio['portfolio_id'],
                    "name": portfolio['portfolio_name'],
                    "current_value": portfolio['current_value'],
                    "ytd_return": portfolio['ytd_return'],
                    "risk_level": portfolio['risk_level']
                })
            
            return {
                "statusCode": 200,
                "body": json.dumps({
                    "client_id": client_id,
                    "total_portfolio_value": f"${total_value:,.2f}",
                    "number_of_portfolios": len(portfolios),
                    "portfolios": portfolio_summary,
                    "summary": f"Client has {len(portfolios)} portfolios with total value of ${total_value:,.2f}"
                })
            }
        else:
            return {
                "statusCode": 404,
                "body": json.dumps({"error": f"No portfolios found for client {client_id}"})
            }
            
    except Exception as e:
        print(f"Error retrieving portfolio summary: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": f"Database error: {str(e)}"})
        }
