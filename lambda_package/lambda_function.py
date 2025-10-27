from check_warranty import check_warranty_status
from get_customer_profile import get_customer_profile
from get_client_profile import get_client_profile
from get_portfolio_summary import get_portfolio_summary


def get_named_parameter(event, name):
    if name not in event:
        return None
    return event.get(name)


def lambda_handler(event, context):
    print(f"Event: {event}")
    print(f"Context: {context}")

    extended_tool_name = context.client_context.custom["bedrockAgentCoreToolName"]
    resource = extended_tool_name.split("___")[1]
    
    # Extract tenant_id from headers (passed by MCP client)
    tenant_id = None
    if 'headers' in event:
        tenant_id = event['headers'].get('X-Tenant-ID', event['headers'].get('x-tenant-id'))
    
    # Fallback: try to get from event body or default to basic
    if not tenant_id and 'tenant_id' in event:
        tenant_id = event.get('tenant_id')
    
    tenant_id = tenant_id or 'basic'  # Default to basic tenant
    
    print(f"🔍 Processing request for tenant: {tenant_id}, resource: {resource}")

    # Route to tenant-specific functions
    if tenant_id == 'basic':
        # Gaming console company tools
        if resource == "get_customer_profile":
            customer_id = get_named_parameter(event=event, name="customer_id")
            email = get_named_parameter(event=event, name="email")
            phone = get_named_parameter(event=event, name="phone")

            if not customer_id:
                return {
                    "statusCode": 400,
                    "body": "❌ Please provide customer_id",
                }

            try:
                customer_profile = get_customer_profile(
                    customer_id=customer_id, email=email, phone=phone
                )
            except Exception as e:
                print(e)
                return {
                    "statusCode": 400,
                    "body": f"❌ {e}",
                }

            return {
                "statusCode": 200,
                "body": f"👤 Customer Profile Information: {customer_profile}",
            }

        elif resource == "check_warranty_status":
            serial_number = get_named_parameter(event=event, name="serial_number")
            customer_email = get_named_parameter(event=event, name="customer_email")

            if not serial_number:
                return {
                    "statusCode": 400,
                    "body": "❌ Please provide serial_number",
                }

            try:
                warranty_status = check_warranty_status(
                    serial_number=serial_number, customer_email=customer_email
                )
            except Exception as e:
                print(e)
                return {
                    "statusCode": 400,
                    "body": f"❌ {e}",
                }

            return {
                "statusCode": 200,
                "body": warranty_status,
            }
    
    elif tenant_id == 'premium':
        # Financial company tools
        if resource == "get_client_profile":
            client_id = get_named_parameter(event, "client_id")
            if not client_id:
                return {
                    "statusCode": 400,
                    "body": "❌ Please provide client_id",
                }
            return get_client_profile(client_id)
            
        elif resource == "get_portfolio_summary":
            client_id = get_named_parameter(event, "client_id")
            if not client_id:
                return {
                    "statusCode": 400,
                    "body": "❌ Please provide client_id",
                }
            return get_portfolio_summary(client_id)

    # If we get here, the tool is not available for this tenant
    return {
        "statusCode": 403,
        "body": f"❌ Tool '{resource}' not available for {tenant_id} tier",
    }
