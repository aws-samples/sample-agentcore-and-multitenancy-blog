#!/usr/bin/python
"""
AgentCore Policy Management for Healthcare Multi-Tenancy

Creates and manages policy engines with Cedar policies for the premium gateway.
Implements business hours enforcement on patient_context tool access.

Usage:
    python scripts/agentcore_policy.py create    # Create policy engine + policies, attach to premium gateway
    python scripts/agentcore_policy.py delete    # Detach and delete policy engine + policies
    python scripts/agentcore_policy.py status    # Show current policy engine status
"""

import sys
import time
import boto3
import click

from utils import (
    get_aws_region,
    get_ssm_parameter,
    put_ssm_parameter,
    delete_ssm_parameter,
)

REGION = get_aws_region()

policy_client = boto3.client("bedrock-agentcore-control", region_name=REGION)
gateway_client = boto3.client("bedrock-agentcore-control", region_name=REGION)


def get_business_hours_cedar_policy(gateway_arn: str, target_name: str) -> str:
    """
    Generate Cedar policy that restricts patient_context access to business hours (8am-6pm).
    
    The policy uses the request_hour field from the tool input schema.
    The agent is expected to pass the current hour (0-23) when calling patient_context.
    Uses 'has' guard to safely check for the optional request_hour field before comparison.
    
    Action format: TargetName___ToolName (triple underscore per AgentCore schema)
    
    Args:
        gateway_arn: ARN of the premium gateway
        target_name: Name of the gateway target (e.g., "HealthcareLambda-Premium")
    """
    return f"""permit(
  principal,
  action == AgentCore::Action::"{target_name}___patient_context",
  resource == AgentCore::Gateway::"{gateway_arn}"
)
when {{
  context.input has request_hour &&
  context.input.request_hour >= 8 &&
  context.input.request_hour < 18
}};"""


def get_clinic_config_permit_policy(gateway_arn: str, target_name: str) -> str:
    """
    Generate Cedar policy that always permits clinic_config access.
    
    clinic_config is non-sensitive configuration data, so no time restriction needed.
    Without an explicit permit, the default-deny behavior would block it.
    
    Action format: TargetName___ToolName (triple underscore per AgentCore schema)
    """
    return f"""permit(
  principal,
  action == AgentCore::Action::"{target_name}___clinic_config",
  resource == AgentCore::Gateway::"{gateway_arn}"
);"""


def wait_for_policy_engine_ready(policy_engine_id: str, max_wait: int = 120) -> bool:
    """Wait for policy engine to become ACTIVE."""
    click.echo(f"⏳ Waiting for policy engine {policy_engine_id} to become ACTIVE...")
    start = time.time()
    while time.time() - start < max_wait:
        try:
            resp = policy_client.get_policy_engine(policyEngineId=policy_engine_id)
            status = resp.get("status")
            if status == "ACTIVE":
                click.echo("✅ Policy engine is ACTIVE")
                return True
            elif status in ["FAILED", "DELETING"]:
                click.echo(f"❌ Policy engine entered {status} state", err=True)
                return False
            time.sleep(5)
        except Exception as e:
            click.echo(f"❌ Error checking policy engine: {e}", err=True)
            return False
    click.echo("❌ Timeout waiting for policy engine", err=True)
    return False


def get_gateway_target_name(gateway_id: str) -> str:
    """Get the target name for the premium gateway (needed for Cedar action format)."""
    resp = gateway_client.list_gateway_targets(gatewayIdentifier=gateway_id, maxResults=10)
    items = resp.get("items", [])
    if not items:
        raise Exception(f"No targets found for gateway {gateway_id}")
    return items[0]["name"]


@click.group()
def cli():
    """AgentCore Policy Management for Healthcare Premium Tier."""
    pass


@cli.command()
def create():
    """Create policy engine with business hours policy and attach to premium gateway."""
    click.echo("🛡️  Creating AgentCore Policy for Premium Gateway")
    click.echo(f"📍 Region: {REGION}")

    # Get premium gateway info from SSM
    try:
        gateway_id = get_ssm_parameter("/app/healthcare/agentcore/premium_gateway_id")
        gateway_arn = get_ssm_parameter("/app/healthcare/agentcore/premium_gateway_arn")
    except Exception as e:
        click.echo(f"❌ Premium gateway not found in SSM. Deploy gateways first: {e}", err=True)
        sys.exit(1)

    click.echo(f"🔗 Premium Gateway: {gateway_id}")

    # Get target name for Cedar action format
    try:
        target_name = get_gateway_target_name(gateway_id)
        click.echo(f"🎯 Gateway Target: {target_name}")
    except Exception as e:
        click.echo(f"❌ Could not get gateway target: {e}", err=True)
        sys.exit(1)

    # Step 1: Create policy engine
    click.echo("\n📋 Step 1: Creating policy engine...")
    try:
        resp = policy_client.create_policy_engine(
            name="healthcare_premium_policy_engine",
            description="Business hours enforcement for premium healthcare agent tools",
        )
        policy_engine_id = resp["policyEngineId"]
        policy_engine_arn = resp["policyEngineArn"]
        click.echo(f"✅ Policy engine created: {policy_engine_id}")
    except policy_client.exceptions.ConflictException:
        click.echo("⚠️  Policy engine already exists, looking up...")
        # List and find existing
        resp = policy_client.list_policy_engines(maxResults=50)
        found = None
        for engine in resp.get("policyEngines", []):
            if engine.get("name") == "healthcare_premium_policy_engine":
                found = engine
                break
        if not found:
            click.echo("❌ Could not find existing policy engine", err=True)
            sys.exit(1)
        policy_engine_id = found["policyEngineId"]
        policy_engine_arn = found["policyEngineArn"]
        click.echo(f"✅ Found existing policy engine: {policy_engine_id}")

    # Wait for policy engine to be ready
    if not wait_for_policy_engine_ready(policy_engine_id):
        sys.exit(1)

    # Step 2: Create Cedar policies
    click.echo("\n📋 Step 2: Creating Cedar policies...")

    # Business hours policy for patient_context
    business_hours_cedar = get_business_hours_cedar_policy(gateway_arn, target_name)
    click.echo(f"\n--- Business Hours Policy (patient_context) ---")
    click.echo(business_hours_cedar)
    click.echo("---")

    try:
        resp = policy_client.create_policy(
            policyEngineId=policy_engine_id,
            name="business_hours_patient_access",
            definition={"cedar": {"statement": business_hours_cedar}},
            description="Restrict patient_context access to business hours (8am-6pm)",
        )
        click.echo(f"✅ Business hours policy created: {resp['policyId']}")
        put_ssm_parameter("/app/healthcare/agentcore/policy_business_hours_id", resp["policyId"])
    except policy_client.exceptions.ConflictException:
        click.echo("⚠️  Business hours policy already exists, skipping...")
    except Exception as e:
        click.echo(f"❌ Failed to create business hours policy: {e}", err=True)
        sys.exit(1)

    # Permit policy for clinic_config (no time restriction)
    clinic_config_cedar = get_clinic_config_permit_policy(gateway_arn, target_name)
    click.echo(f"\n--- Clinic Config Permit Policy ---")
    click.echo(clinic_config_cedar)
    click.echo("---")

    try:
        resp = policy_client.create_policy(
            policyEngineId=policy_engine_id,
            name="permit_clinic_config",
            definition={"cedar": {"statement": clinic_config_cedar}},
            description="Always permit clinic_config access (non-sensitive data)",
        )
        click.echo(f"✅ Clinic config permit policy created: {resp['policyId']}")
        put_ssm_parameter("/app/healthcare/agentcore/policy_clinic_config_id", resp["policyId"])
    except policy_client.exceptions.ConflictException:
        click.echo("⚠️  Clinic config policy already exists, skipping...")
    except Exception as e:
        click.echo(f"❌ Failed to create clinic config policy: {e}", err=True)
        sys.exit(1)

    # Step 3: Attach policy engine to premium gateway
    click.echo("\n📋 Step 3: Attaching policy engine to premium gateway...")
    try:
        # update_gateway requires all original fields — fetch them first
        gw_details = gateway_client.get_gateway(gatewayIdentifier=gateway_id)
        
        update_params = {
            "gatewayIdentifier": gateway_id,
            "name": gw_details["name"],
            "roleArn": gw_details["roleArn"],
            "protocolType": gw_details["protocolType"],
            "authorizerType": gw_details["authorizerType"],
            "policyEngineConfiguration": {
                "arn": policy_engine_arn,
                "mode": "ENFORCE",
            },
        }
        
        # Preserve existing authorizer config if present
        if "authorizerConfiguration" in gw_details:
            update_params["authorizerConfiguration"] = gw_details["authorizerConfiguration"]
        
        gateway_client.update_gateway(**update_params)
        click.echo(f"✅ Policy engine attached to gateway in ENFORCE mode")
    except Exception as e:
        click.echo(f"❌ Failed to attach policy engine: {e}", err=True)
        sys.exit(1)

    # Save to SSM
    put_ssm_parameter("/app/healthcare/agentcore/policy_engine_id", policy_engine_id)
    put_ssm_parameter("/app/healthcare/agentcore/policy_engine_arn", policy_engine_arn)

    click.echo("\n" + "=" * 60)
    click.echo("🎉 AgentCore Policy setup complete!")
    click.echo("=" * 60)
    click.echo(f"Policy Engine: {policy_engine_id}")
    click.echo(f"Mode: ENFORCE")
    click.echo(f"Policies:")
    click.echo(f"  - business_hours_patient_access: patient_context restricted to 8am-6pm")
    click.echo(f"  - permit_clinic_config: clinic_config always permitted")


@cli.command()
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
def delete(confirm):
    """Detach policy engine from gateway and delete all policies."""
    click.echo("🗑️  Deleting AgentCore Policy configuration")

    if not confirm:
        if not click.confirm("⚠️  Delete policy engine and all policies?"):
            click.echo("Cancelled")
            sys.exit(0)

    # Get policy engine ID
    try:
        policy_engine_id = get_ssm_parameter("/app/healthcare/agentcore/policy_engine_id")
    except Exception:
        click.echo("⚠️  No policy engine found in SSM")
        return

    # Detach from gateway first
    try:
        gateway_id = get_ssm_parameter("/app/healthcare/agentcore/premium_gateway_id")
        gw_details = gateway_client.get_gateway(gatewayIdentifier=gateway_id)
        gateway_client.update_gateway(
            gatewayIdentifier=gateway_id,
            name=gw_details["name"],
            roleArn=gw_details["roleArn"],
            protocolType=gw_details["protocolType"],
            authorizerType=gw_details["authorizerType"],
            policyEngineConfiguration={},
        )
        click.echo(f"✅ Policy engine detached from gateway {gateway_id}")
    except Exception as e:
        click.echo(f"⚠️  Could not detach from gateway: {e}")

    # Delete policies
    try:
        resp = policy_client.list_policies(policyEngineId=policy_engine_id, maxResults=50)
        for policy in resp.get("policies", []):
            policy_client.delete_policy(
                policyEngineId=policy_engine_id,
                policyId=policy["policyId"],
            )
            click.echo(f"✅ Deleted policy: {policy.get('name', policy['policyId'])}")
    except Exception as e:
        click.echo(f"⚠️  Error deleting policies: {e}")

    # Delete policy engine
    try:
        policy_client.delete_policy_engine(policyEngineId=policy_engine_id)
        click.echo(f"✅ Policy engine {policy_engine_id} deleted")
    except Exception as e:
        click.echo(f"❌ Error deleting policy engine: {e}", err=True)

    # Clean up SSM
    delete_ssm_parameter("/app/healthcare/agentcore/policy_engine_id")
    delete_ssm_parameter("/app/healthcare/agentcore/policy_engine_arn")
    delete_ssm_parameter("/app/healthcare/agentcore/policy_business_hours_id")
    delete_ssm_parameter("/app/healthcare/agentcore/policy_clinic_config_id")
    click.echo("🧹 SSM parameters cleaned up")


@cli.command()
def status():
    """Show current policy engine status and policies."""
    click.echo("📋 AgentCore Policy Status")
    click.echo("=" * 60)

    try:
        policy_engine_id = get_ssm_parameter("/app/healthcare/agentcore/policy_engine_id")
    except Exception:
        click.echo("No policy engine configured")
        return

    try:
        resp = policy_client.get_policy_engine(policyEngineId=policy_engine_id)
        click.echo(f"Policy Engine: {policy_engine_id}")
        click.echo(f"Name: {resp.get('name')}")
        click.echo(f"Status: {resp.get('status')}")
        click.echo(f"ARN: {resp.get('policyEngineArn')}")
    except Exception as e:
        click.echo(f"Error getting policy engine: {e}")
        return

    # List policies
    try:
        resp = policy_client.list_policies(policyEngineId=policy_engine_id, maxResults=50)
        policies = resp.get("policies", [])
        click.echo(f"\nPolicies ({len(policies)}):")
        for p in policies:
            click.echo(f"  - {p.get('name', 'unnamed')} ({p['policyId']})")
    except Exception as e:
        click.echo(f"Error listing policies: {e}")

    # Check gateway attachment
    try:
        gateway_id = get_ssm_parameter("/app/healthcare/agentcore/premium_gateway_id")
        gw_resp = gateway_client.get_gateway(gatewayIdentifier=gateway_id)
        policy_config = gw_resp.get("policyEngineConfiguration", {})
        if policy_config:
            click.echo(f"\nGateway Attachment:")
            click.echo(f"  Gateway: {gateway_id}")
            click.echo(f"  Mode: {policy_config.get('mode', 'N/A')}")
        else:
            click.echo(f"\n⚠️  Policy engine not attached to gateway")
    except Exception as e:
        click.echo(f"Error checking gateway: {e}")


if __name__ == "__main__":
    cli()
