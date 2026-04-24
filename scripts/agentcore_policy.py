#!/usr/bin/python
# Copyright 2026 Amazon.com and its affiliates; all rights reserved.
# SPDX-License-Identifier: MIT-0

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
  principal is AgentCore::OAuthUser,
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
    Generate Cedar policies that permit clinic_config access for authenticated users.
    
    clinic_config is non-sensitive configuration data, so no time restriction needed.
    Without an explicit permit, the default-deny behavior would block it.
    
    AgentCore's policy validator rejects unconditional permits as "overly permissive",
    so we split into two complementary policies that together cover all cases:
    - One permits when clinic_id IS provided in the input
    - One permits when clinic_id is NOT provided (uses default clinic)
    
    Returns a list of (name_suffix, cedar_statement, description) tuples.
    
    Action format: TargetName___ToolName (triple underscore per AgentCore schema)
    """
    policy_with_id = f"""permit(
  principal is AgentCore::OAuthUser,
  action == AgentCore::Action::"{target_name}___clinic_config",
  resource == AgentCore::Gateway::"{gateway_arn}"
)
when {{
  context.input has clinic_id
}};"""

    policy_without_id = f"""permit(
  principal is AgentCore::OAuthUser,
  action == AgentCore::Action::"{target_name}___clinic_config",
  resource == AgentCore::Gateway::"{gateway_arn}"
)
when {{
  !(context.input has clinic_id)
}};"""

    return [
        ("with_id", policy_with_id, "Permit clinic_config when clinic_id is provided"),
        ("default", policy_without_id, "Permit clinic_config when using default clinic (no clinic_id)"),
    ]


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


def _create_policies_for_gateway(policy_engine_id: str, gateway_arn: str, target_name: str, tier: str):
    """Create Cedar policies (business hours + clinic_config permits) for a single gateway.

    Args:
        policy_engine_id: ID of the shared policy engine.
        gateway_arn: ARN of the gateway to create policies for.
        target_name: Gateway target name (e.g., "HealthcareLambda-Basic").
        tier: Tier label used for naming ("basic" or "premium").
    """
    # Business hours policy for patient_context
    business_hours_cedar = get_business_hours_cedar_policy(gateway_arn, target_name)
    policy_name = f"business_hours_patient_access_{tier}"
    click.echo(f"\n--- Business Hours Policy ({tier} / patient_context) ---")
    click.echo(business_hours_cedar)
    click.echo("---")

    try:
        resp = policy_client.create_policy(
            policyEngineId=policy_engine_id,
            name=policy_name,
            definition={"cedar": {"statement": business_hours_cedar}},
            description=f"Restrict {tier} patient_context access to business hours (8am-6pm)",
        )
        click.echo(f"✅ Business hours policy ({tier}) created: {resp['policyId']}")
        put_ssm_parameter(f"/app/healthcare/agentcore/policy_business_hours_{tier}_id", resp["policyId"])
    except policy_client.exceptions.ConflictException:
        click.echo(f"⚠️  Business hours policy ({tier}) already exists, skipping...")
    except Exception as e:
        click.echo(f"❌ Failed to create business hours policy ({tier}): {e}", err=True)
        sys.exit(1)

    # Permit policies for clinic_config (no time restriction)
    clinic_config_policies = get_clinic_config_permit_policy(gateway_arn, target_name)

    for suffix, cedar_statement, description in clinic_config_policies:
        policy_name = f"permit_clinic_config_{tier}_{suffix}"
        click.echo(f"\n--- Clinic Config Policy ({tier} / {suffix}) ---")
        click.echo(cedar_statement)
        click.echo("---")

        try:
            resp = policy_client.create_policy(
                policyEngineId=policy_engine_id,
                name=policy_name,
                definition={"cedar": {"statement": cedar_statement}},
                description=f"{description} ({tier})",
            )
            click.echo(f"✅ Clinic config policy ({tier}/{suffix}) created: {resp['policyId']}")
            put_ssm_parameter(f"/app/healthcare/agentcore/policy_clinic_config_{tier}_{suffix}_id", resp["policyId"])
        except policy_client.exceptions.ConflictException:
            click.echo(f"⚠️  Clinic config policy ({tier}/{suffix}) already exists, skipping...")
        except Exception as e:
            click.echo(f"❌ Failed to create clinic config policy ({tier}/{suffix}): {e}", err=True)
            sys.exit(1)


def _attach_policy_engine_to_gateway(gateway_id: str, policy_engine_arn: str, tier: str):
    """Attach a policy engine to a gateway in ENFORCE mode.

    Args:
        gateway_id: Gateway identifier.
        policy_engine_arn: ARN of the policy engine to attach.
        tier: Tier label for logging ("basic" or "premium").
    """
    click.echo(f"\n📎 Attaching policy engine to {tier} gateway ({gateway_id})...")
    try:
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

        if "authorizerConfiguration" in gw_details:
            update_params["authorizerConfiguration"] = gw_details["authorizerConfiguration"]

        gateway_client.update_gateway(**update_params)
        click.echo(f"✅ Policy engine attached to {tier} gateway in ENFORCE mode")
    except Exception as e:
        click.echo(f"❌ Failed to attach policy engine to {tier} gateway: {e}", err=True)
        sys.exit(1)


@click.group()
def cli():
    """AgentCore Policy Management for Healthcare Gateways (Basic + Premium)."""
    pass


@cli.command()
def create():
    """Create policy engine with business hours policies and attach to both gateways."""
    click.echo("🛡️  Creating AgentCore Policy for Basic + Premium Gateways")
    click.echo(f"📍 Region: {REGION}")

    # Gather gateway info for both tiers
    gateways = {}
    for tier in ("basic", "premium"):
        try:
            gw_id = get_ssm_parameter(f"/app/healthcare/agentcore/{tier}_gateway_id")
            gw_arn = get_ssm_parameter(f"/app/healthcare/agentcore/{tier}_gateway_arn")
            target = get_gateway_target_name(gw_id)
            gateways[tier] = {"id": gw_id, "arn": gw_arn, "target": target}
            click.echo(f"🔗 {tier.capitalize()} Gateway: {gw_id}  (target: {target})")
        except Exception as e:
            click.echo(f"❌ {tier.capitalize()} gateway not found in SSM. Deploy gateways first: {e}", err=True)
            sys.exit(1)

    # Step 1: Create (or find) shared policy engine
    click.echo("\n📋 Step 1: Creating policy engine...")
    try:
        resp = policy_client.create_policy_engine(
            name="healthcare_policy_engine",
            description="Business hours enforcement for healthcare agent tools (all tiers)",
        )
        policy_engine_id = resp["policyEngineId"]
        policy_engine_arn = resp["policyEngineArn"]
        click.echo(f"✅ Policy engine created: {policy_engine_id}")
    except policy_client.exceptions.ConflictException:
        click.echo("⚠️  Policy engine already exists, looking up...")
        resp = policy_client.list_policy_engines(maxResults=50)
        found = None
        for engine in resp.get("policyEngines", []):
            if engine.get("name") in ("healthcare_policy_engine", "healthcare_premium_policy_engine"):
                found = engine
                break
        if not found:
            click.echo("❌ Could not find existing policy engine", err=True)
            sys.exit(1)
        policy_engine_id = found["policyEngineId"]
        policy_engine_arn = found["policyEngineArn"]
        click.echo(f"✅ Found existing policy engine: {policy_engine_id}")

    if not wait_for_policy_engine_ready(policy_engine_id):
        sys.exit(1)

    # Step 2: Create Cedar policies for each gateway
    click.echo("\n📋 Step 2: Creating Cedar policies...")
    for tier, gw in gateways.items():
        _create_policies_for_gateway(policy_engine_id, gw["arn"], gw["target"], tier)

    # Step 3: Attach policy engine to both gateways
    click.echo("\n📋 Step 3: Attaching policy engine to gateways...")
    for tier, gw in gateways.items():
        _attach_policy_engine_to_gateway(gw["id"], policy_engine_arn, tier)

    # Save to SSM
    put_ssm_parameter("/app/healthcare/agentcore/policy_engine_id", policy_engine_id)
    put_ssm_parameter("/app/healthcare/agentcore/policy_engine_arn", policy_engine_arn)

    click.echo("\n" + "=" * 60)
    click.echo("🎉 AgentCore Policy setup complete!")
    click.echo("=" * 60)
    click.echo(f"Policy Engine: {policy_engine_id}")
    click.echo(f"Mode: ENFORCE")
    click.echo(f"Gateways: basic + premium")
    click.echo(f"Policies (per gateway):")
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

    # Detach from both gateways
    for tier in ("basic", "premium"):
        try:
            gateway_id = get_ssm_parameter(f"/app/healthcare/agentcore/{tier}_gateway_id")
            gw_details = gateway_client.get_gateway(gatewayIdentifier=gateway_id)

            update_params = {
                "gatewayIdentifier": gateway_id,
                "name": gw_details["name"],
                "roleArn": gw_details["roleArn"],
                "protocolType": gw_details["protocolType"],
                "authorizerType": gw_details["authorizerType"],
            }
            if "authorizerConfiguration" in gw_details:
                update_params["authorizerConfiguration"] = gw_details["authorizerConfiguration"]

            gateway_client.update_gateway(**update_params)
            click.echo(f"✅ Policy engine detached from {tier} gateway {gateway_id}")
        except Exception as e:
            click.echo(f"⚠️  Could not detach from {tier} gateway: {e}")

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
    for tier in ("basic", "premium"):
        delete_ssm_parameter(f"/app/healthcare/agentcore/policy_business_hours_{tier}_id")
        delete_ssm_parameter(f"/app/healthcare/agentcore/policy_clinic_config_{tier}_with_id_id")
        delete_ssm_parameter(f"/app/healthcare/agentcore/policy_clinic_config_{tier}_default_id")
    # Legacy keys from premium-only setup
    delete_ssm_parameter("/app/healthcare/agentcore/policy_business_hours_id")
    delete_ssm_parameter("/app/healthcare/agentcore/policy_clinic_config_id")
    delete_ssm_parameter("/app/healthcare/agentcore/policy_clinic_config_with_id_id")
    delete_ssm_parameter("/app/healthcare/agentcore/policy_clinic_config_default_id")
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

    # Check gateway attachments
    for tier in ("basic", "premium"):
        try:
            gateway_id = get_ssm_parameter(f"/app/healthcare/agentcore/{tier}_gateway_id")
            gw_resp = gateway_client.get_gateway(gatewayIdentifier=gateway_id)
            policy_config = gw_resp.get("policyEngineConfiguration", {})
            if policy_config:
                click.echo(f"\n{tier.capitalize()} Gateway Attachment:")
                click.echo(f"  Gateway: {gateway_id}")
                click.echo(f"  Mode: {policy_config.get('mode', 'N/A')}")
            else:
                click.echo(f"\n⚠️  Policy engine not attached to {tier} gateway")
        except Exception as e:
            click.echo(f"⚠️  Error checking {tier} gateway: {e}")


if __name__ == "__main__":
    cli()
