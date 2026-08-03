#!/usr/bin/python
# Copyright 2026 Amazon.com and its affiliates; all rights reserved.
# SPDX-License-Identifier: MIT-0

from typing import List
import os
import sys
import time
import boto3
import click

from utils import (
    get_aws_region,
    get_ssm_parameter,
    put_ssm_parameter,
    delete_ssm_parameter,
    load_api_spec,
    get_cognito_client_secret,
)


REGION = get_aws_region()

gateway_client = boto3.client(
    "bedrock-agentcore-control",
    region_name=REGION,
)


def wait_for_gateway_active(gateway_id: str, max_wait_seconds: int = 300) -> bool:
    """Wait for gateway to become READY.
    
    Args:
        gateway_id: The gateway ID to wait for
        max_wait_seconds: Maximum time to wait in seconds (default: 300)
        
    Returns:
        True if gateway became ready, False if timeout or error
        
    Valid gateway statuses: CREATING | UPDATING | UPDATE_UNSUCCESSFUL | DELETING | READY | FAILED
    """
    click.echo(f"⏳ Waiting for gateway {gateway_id} to become READY...")
    start_time = time.time()
    
    while time.time() - start_time < max_wait_seconds:
        try:
            response = gateway_client.get_gateway(gatewayIdentifier=gateway_id)
            status = response.get("status")
            
            if status == "READY":
                click.echo(f"✅ Gateway is now READY")
                return True
            elif status in ["FAILED", "UPDATE_UNSUCCESSFUL", "DELETING"]:
                click.echo(f"❌ Gateway entered {status} state", err=True)
                return False
            elif status in ["CREATING", "UPDATING"]:
                # Still in progress, wait a bit
                time.sleep(5)
            else:
                click.echo(f"⚠️  Unknown gateway status: {status}", err=True)
                time.sleep(5)
            
        except Exception as e:
            click.echo(f"❌ Error checking gateway status: {str(e)}", err=True)
            return False
    
    click.echo(f"❌ Timeout waiting for gateway to become READY", err=True)
    return False


def wait_for_target_ready(gateway_id: str, target_id: str, max_wait_seconds: int = 180) -> bool:
    """Wait for a gateway target to become READY.

    The managed knowledge base connector validates its configuration
    asynchronously (including a GetKnowledgeBase check on the bound KB),
    so a freshly created target starts in a non-ready state.

    Valid target statuses: CREATING | UPDATING | READY | FAILED
    """
    click.echo(f"⏳ Waiting for target {target_id} to become READY...")
    start_time = time.time()
    while time.time() - start_time < max_wait_seconds:
        try:
            response = gateway_client.get_gateway_target(
                gatewayIdentifier=gateway_id, targetId=target_id
            )
            status = response.get("status")
            if status == "READY":
                click.echo(f"✅ Target {target_id} is now READY")
                return True
            elif status == "FAILED":
                reason = response.get("statusReasons") or response.get("statusReason") or ""
                click.echo(f"❌ Target {target_id} entered FAILED state: {reason}", err=True)
                return False
            time.sleep(5)
        except Exception as e:
            click.echo(f"❌ Error checking target status: {str(e)}", err=True)
            return False
    click.echo(f"❌ Timeout waiting for target {target_id} to become READY", err=True)
    return False


def _build_lambda_target_config(api_spec: List) -> dict:
    """Build the Lambda target configuration (patient_context, clinic_config tools)."""
    return {
        "mcp": {
            "lambda": {
                "lambdaArn": get_ssm_parameter("/app/healthcare/agentcore/lambda_arn"),
                "toolSchema": {"inlinePayload": api_spec},
            }
        }
    }


def _build_kb_target_config(kb_id: str) -> dict:
    """Build the Amazon Bedrock Managed Knowledge Bases connector target config.

    Tenant isolation model (pool tenancy):
      - knowledgeBaseId is bound here in parameterValues and never exposed to the
        caller — one shared KB per tier.
      - The clinic_id metadata filter is applied per request. The filter path is
        exposed via parameterOverrides so the *application* (trusted wrapper code
        in agent.py) can set it from the validated tenant context. The raw
        `Retrieve` tool is never registered into the model's toolset, so the LLM
        cannot set or override the filter itself.
    """
    return {
        "mcp": {
            "connector": {
                "source": {"connectorId": "bedrock-knowledge-bases"},
                "configurations": [
                    {
                        "name": "Retrieve",
                        "description": (
                            "Search the clinic knowledge base for clinical documents. "
                            "The tenant metadata filter is applied by the application."
                        ),
                        "parameterValues": {
                            "knowledgeBaseId": kb_id,
                            "retrievalConfiguration": {
                                "managedSearchConfiguration": {
                                    "numberOfResults": 5,
                                }
                            },
                        },
                        "parameterOverrides": [
                            {
                                "path": "$.retrievalQuery.text",
                                "description": "The search query text.",
                                "visible": True,
                            },
                            {
                                "path": "$.retrievalConfiguration.managedSearchConfiguration.filter",
                                "description": (
                                    "Metadata filter applied to the search. Set by the "
                                    "application to enforce clinic-level tenant isolation."
                                ),
                                "visible": True,
                            },
                            {
                                "path": "$.retrievalConfiguration.managedSearchConfiguration.numberOfResults",
                                "description": "Number of results to retrieve (1-100).",
                                "visible": True,
                            },
                        ],
                    }
                ],
            }
        }
    }


def _existing_targets(gateway_id: str) -> dict:
    """Return a map of target name -> {id, status} already present on the gateway."""
    targets = {}
    try:
        resp = gateway_client.list_gateway_targets(gatewayIdentifier=gateway_id, maxResults=100)
        for item in resp.get("items", []):
            targets[item.get("name")] = {
                "id": item.get("targetId"),
                "status": item.get("status"),
            }
    except Exception as e:
        click.echo(f"⚠️  Could not list existing targets: {e}")
    return targets


def ensure_targets(gateway_id: str, api_spec: List, tier: str) -> None:
    """Ensure both the Lambda tool target and the managed KB target exist.

    Idempotent: creates whichever target is missing and skips those already in a
    good state. A KB target left in a FAILED (or otherwise non-READY) state — for
    example from an earlier run against an incompatible KB type — is deleted and
    recreated. Used by both the fresh-create and existing-gateway code paths.
    """
    existing = _existing_targets(gateway_id)

    lambda_target_name = f"HealthcareLambda-{tier.title()}"
    kb_target_name = f"HealthcareKB-{tier.title()}"

    # --- Lambda tool target (patient_context, clinic_config) ---
    if lambda_target_name in existing:
        click.echo(f"✅ Lambda target already exists: {lambda_target_name}")
    else:
        metadata_config = {
            "allowedRequestHeaders": ["X-Tier", "X-Clinic-ID", "X-S3-Prefix"]
        }
        resp = gateway_client.create_gateway_target(
            gatewayIdentifier=gateway_id,
            name=lambda_target_name,
            description=f"Healthcare Lambda Target - {tier.title()} Tier",
            targetConfiguration=_build_lambda_target_config(api_spec),
            credentialProviderConfigurations=[{"credentialProviderType": "GATEWAY_IAM_ROLE"}],
            metadataConfiguration=metadata_config,
        )
        click.echo(f"✅ Lambda target created: {resp['targetId']}")
        click.echo(f"✅ Header propagation enabled: X-Tier, X-Clinic-ID, X-S3-Prefix")

    # --- Managed Knowledge Base connector target (Retrieve) ---
    kb_existing = existing.get(kb_target_name)
    if kb_existing and kb_existing.get("status") == "READY":
        click.echo(f"✅ KB target already exists and is READY: {kb_target_name}")
    else:
        # Delete a stale/failed KB target so we can recreate it cleanly.
        if kb_existing:
            click.echo(
                f"♻️  KB target {kb_target_name} exists in state "
                f"{kb_existing.get('status')} — deleting and recreating..."
            )
            try:
                gateway_client.delete_gateway_target(
                    gatewayIdentifier=gateway_id, targetId=kb_existing["id"]
                )
            except Exception as e:
                click.echo(f"⚠️  Could not delete stale KB target: {e}")

        try:
            kb_id = get_ssm_parameter(f"/app/healthcare/knowledge_base/{tier}_kb_id")
        except Exception as e:
            click.echo(
                f"❌ Could not read KB id for tier '{tier}' from SSM "
                f"(/app/healthcare/knowledge_base/{tier}_kb_id): {e}",
                err=True,
            )
            sys.exit(1)

        resp = gateway_client.create_gateway_target(
            gatewayIdentifier=gateway_id,
            name=kb_target_name,
            description=f"Healthcare Managed KB Target - {tier.title()} Tier",
            targetConfiguration=_build_kb_target_config(kb_id),
            credentialProviderConfigurations=[{"credentialProviderType": "GATEWAY_IAM_ROLE"}],
        )
        kb_target_id = resp["targetId"]
        click.echo(f"✅ KB target created: {kb_target_id} (KB: {kb_id})")
        # Connector targets validate asynchronously (GetKnowledgeBase check).
        if not wait_for_target_ready(gateway_id, kb_target_id):
            click.echo(
                "❌ KB target did not become READY — check the Gateway execution "
                "role has bedrock:GetKnowledgeBase / bedrock:Retrieve on the KB.",
                err=True,
            )
            sys.exit(1)


def create_gateway(gateway_name: str, api_spec: List, tier: str = "basic") -> dict:
    """Create an AgentCore gateway with the specified configuration.
    
    Args:
        gateway_name: Name of the gateway (e.g., 'healthcare-basic-gw')
        api_spec: API specification for the gateway tools
        tier: Tier level ('basic' or 'premium') for SSM parameter paths
    """
    try:
        execution_role_arn = get_ssm_parameter(
            "/app/healthcare/agentcore/gateway_iam_role"
        )

        click.echo(f"Creating gateway in region {REGION} with name: {gateway_name}")
        click.echo(f"Tier: {tier}")
        click.echo(f"Execution role ARN: {execution_role_arn}")

        create_response = gateway_client.create_gateway(
            name=gateway_name,
            roleArn=execution_role_arn,
            protocolType="MCP",
            authorizerType="CUSTOM_JWT",
            authorizerConfiguration={
                "customJWTAuthorizer": {
                    "discoveryUrl": get_ssm_parameter(
                        "/app/healthcare/agentcore/cognito_discovery_url"
                    ),
                    "allowedAudience": [
                        get_ssm_parameter(
                            "/app/healthcare/agentcore/web_client_id"
                        )
                    ],
                }
            },
            description=f"Healthcare Clinical Document Processing Gateway - {tier.title()} Tier",
        )

        gateway_id = create_response["gatewayId"]
        click.echo(f"✅ Gateway created: {gateway_id}")
        
        # Wait for gateway to become ACTIVE before creating targets
        if not wait_for_gateway_active(gateway_id):
            click.echo(f"❌ Gateway did not become active, cannot create targets", err=True)
            sys.exit(1)

        # Create both the Lambda tool target and the managed KB connector target
        ensure_targets(gateway_id, api_spec, tier)

        gateway = {
            "id": gateway_id,
            "name": gateway_name,
            "tier": tier,
            "gateway_url": create_response["gatewayUrl"],
            "gateway_arn": create_response["gatewayArn"],
        }

        # Save gateway details to tier-specific SSM parameters
        put_ssm_parameter(f"/app/healthcare/agentcore/{tier}_gateway_id", gateway_id)
        put_ssm_parameter(f"/app/healthcare/agentcore/{tier}_gateway_name", gateway_name)
        put_ssm_parameter(
            f"/app/healthcare/agentcore/{tier}_gateway_arn", create_response["gatewayArn"]
        )
        put_ssm_parameter(
            f"/app/healthcare/agentcore/{tier}_gateway_url", create_response["gatewayUrl"]
        )
        
        # Save shared Cognito secret (only once)
        if tier == "basic":
            put_ssm_parameter(
                "/app/healthcare/agentcore/cognito_secret",
                get_cognito_client_secret(),
                with_encryption=True,
            )

        click.echo(f"✅ Gateway configuration saved to SSM parameters (tier: {tier})")

        return gateway

    except gateway_client.exceptions.ConflictException:
        click.echo(f"ℹ️  Gateway '{gateway_name}' already exists, retrieving existing configuration...")
        # List gateways to find the existing one, then get full details
        paginator = gateway_client.get_paginator('list_gateways')
        for page in paginator.paginate():
            for gw in page.get('items', []):
                if gw['name'] == gateway_name:
                    gateway_id = gw['gatewayId']
                    # Get full gateway details including ARN and URL
                    full_gw = gateway_client.get_gateway(gatewayIdentifier=gateway_id)
                    gateway = {
                        "id": gateway_id,
                        "name": gateway_name,
                        "tier": tier,
                        "gateway_url": full_gw.get("gatewayUrl", ""),
                        "gateway_arn": full_gw.get("gatewayArn", ""),
                    }

                    # Ensure both the Lambda and managed KB targets exist
                    try:
                        if not wait_for_gateway_active(gateway_id):
                            click.echo(f"❌ Gateway not ready, cannot create targets", err=True)
                            sys.exit(1)
                        ensure_targets(gateway_id, api_spec, tier)
                    except SystemExit:
                        raise
                    except Exception as target_err:
                        click.echo(f"⚠️  Could not verify/create gateway targets: {target_err}")

                    # Ensure SSM parameters are up to date
                    put_ssm_parameter(f"/app/healthcare/agentcore/{tier}_gateway_id", gateway_id)
                    put_ssm_parameter(f"/app/healthcare/agentcore/{tier}_gateway_name", gateway_name)
                    if gateway["gateway_arn"]:
                        put_ssm_parameter(f"/app/healthcare/agentcore/{tier}_gateway_arn", gateway["gateway_arn"])
                    if gateway["gateway_url"]:
                        put_ssm_parameter(f"/app/healthcare/agentcore/{tier}_gateway_url", gateway["gateway_url"])

                    if tier == "basic":
                        put_ssm_parameter(
                            "/app/healthcare/agentcore/cognito_secret",
                            get_cognito_client_secret(),
                            with_encryption=True,
                        )

                    click.echo(f"✅ Using existing gateway: {gateway_id}")
                    click.echo(f"✅ SSM parameters updated for tier: {tier}")
                    return gateway
        click.echo(f"❌ Gateway exists but could not be found in listing", err=True)
        sys.exit(1)

    except Exception as e:
        click.echo(f"❌ Error creating gateway: {str(e)}", err=True)
        sys.exit(1)


def delete_gateway(gateway_id: str) -> bool:
    """Delete a gateway and all its targets."""
    try:
        click.echo(f"🗑️  Deleting all targets for gateway: {gateway_id}")

        # List and delete all targets
        list_response = gateway_client.list_gateway_targets(
            gatewayIdentifier=gateway_id, maxResults=100
        )

        for item in list_response["items"]:
            target_id = item["targetId"]
            click.echo(f"   Deleting target: {target_id}")
            gateway_client.delete_gateway_target(
                gatewayIdentifier=gateway_id, targetId=target_id
            )
            click.echo(f"   ✅ Target {target_id} deleted")

        # Delete the gateway
        click.echo(f"🗑️  Deleting gateway: {gateway_id}")
        gateway_client.delete_gateway(gatewayIdentifier=gateway_id)
        click.echo(f"✅ Gateway {gateway_id} deleted successfully")

        return True

    except Exception as e:
        click.echo(f"❌ Error deleting gateway: {str(e)}", err=True)
        return False


def get_gateway_id_from_config(tier: str = "basic") -> str:
    """Get gateway ID from SSM parameter for specified tier."""
    try:
        return get_ssm_parameter(f"/app/healthcare/agentcore/{tier}_gateway_id")
    except Exception as e:
        click.echo(f"❌ Error reading gateway ID from SSM: {str(e)}", err=True)
        return None


@click.group()
@click.pass_context
def cli(ctx):
    """AgentCore Gateway Management CLI for Healthcare Multi-Tenancy.

    Create and manage separate AgentCore gateways for basic and premium tiers
    in the healthcare clinical document processing platform.
    
    Each tier has its own gateway with tier-specific tools:
    - healthcare-basic-gw: Basic tier with document search and summarization
    - healthcare-premium-gw: Premium tier with advanced analytics and web search
    """
    ctx.ensure_object(dict)


@cli.command()
@click.option(
    "--api-spec-file",
    default="prerequisite/lambda/api_spec.json",
    help="Path to the API specification file (default: prerequisite/lambda/api_spec.json)",
)
def create_all(api_spec_file):
    """Create both basic and premium tier gateways.
    
    This is a convenience command that creates:
    - healthcare-basic-gw (basic tier)
    - healthcare-premium-gw (premium tier)
    
    Example:
        python agentcore_gateway.py create-all
    """
    click.echo("🚀 Creating both Healthcare AgentCore gateways")
    click.echo(f"📍 Region: {REGION}")
    
    # Validate API spec file exists
    if not os.path.exists(api_spec_file):
        click.echo(f"❌ API specification file not found: {api_spec_file}", err=True)
        sys.exit(1)
    
    try:
        api_spec = load_api_spec(api_spec_file)
        
        # Create basic tier gateway
        click.echo("\n" + "="*60)
        click.echo("Creating Basic Tier Gateway")
        click.echo("="*60)
        basic_gateway = create_gateway(
            gateway_name="healthcare-basic-gw",
            api_spec=api_spec,
            tier="basic"
        )
        click.echo(f"✅ Basic gateway created: {basic_gateway['id']}")
        click.echo(f"🔗 Basic gateway URL: {basic_gateway['gateway_url']}")
        
        # Create premium tier gateway
        click.echo("\n" + "="*60)
        click.echo("Creating Premium Tier Gateway")
        click.echo("="*60)
        premium_gateway = create_gateway(
            gateway_name="healthcare-premium-gw",
            api_spec=api_spec,
            tier="premium"
        )
        click.echo(f"✅ Premium gateway created: {premium_gateway['id']}")
        click.echo(f"🔗 Premium gateway URL: {premium_gateway['gateway_url']}")
        
        click.echo("\n" + "="*60)
        click.echo("🎉 Both gateways created successfully!")
        click.echo("="*60)
        click.echo(f"Basic Tier:   {basic_gateway['id']}")
        click.echo(f"Premium Tier: {premium_gateway['id']}")
        
    except Exception as e:
        click.echo(f"❌ Failed to create gateways: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
def delete_all(confirm):
    """Delete both basic and premium tier gateways.
    
    Example:
        python agentcore_gateway.py delete-all --confirm
    """
    click.echo("🗑️  Deleting both Healthcare AgentCore gateways")
    
    # Confirmation prompt
    if not confirm:
        if not click.confirm(
            "⚠️  Are you sure you want to delete BOTH gateways? This action cannot be undone."
        ):
            click.echo("❌ Operation cancelled")
            sys.exit(0)
    
    success_count = 0
    
    # Delete basic tier gateway
    basic_gw_id = get_gateway_id_from_config("basic")
    if basic_gw_id:
        click.echo(f"\n🗑️  Deleting basic tier gateway: {basic_gw_id}")
        if delete_gateway(basic_gw_id):
            delete_ssm_parameter("/app/healthcare/agentcore/basic_gateway_id")
            delete_ssm_parameter("/app/healthcare/agentcore/basic_gateway_name")
            delete_ssm_parameter("/app/healthcare/agentcore/basic_gateway_arn")
            delete_ssm_parameter("/app/healthcare/agentcore/basic_gateway_url")
            click.echo("✅ Basic tier gateway deleted")
            success_count += 1
        else:
            click.echo("❌ Failed to delete basic tier gateway", err=True)
    else:
        click.echo("⚠️  No basic tier gateway found")
    
    # Delete premium tier gateway
    premium_gw_id = get_gateway_id_from_config("premium")
    if premium_gw_id:
        click.echo(f"\n🗑️  Deleting premium tier gateway: {premium_gw_id}")
        if delete_gateway(premium_gw_id):
            delete_ssm_parameter("/app/healthcare/agentcore/premium_gateway_id")
            delete_ssm_parameter("/app/healthcare/agentcore/premium_gateway_name")
            delete_ssm_parameter("/app/healthcare/agentcore/premium_gateway_arn")
            delete_ssm_parameter("/app/healthcare/agentcore/premium_gateway_url")
            click.echo("✅ Premium tier gateway deleted")
            success_count += 1
        else:
            click.echo("❌ Failed to delete premium tier gateway", err=True)
    else:
        click.echo("⚠️  No premium tier gateway found")
    
    # Clean up shared resources
    if success_count > 0:
        delete_ssm_parameter("/app/healthcare/agentcore/cognito_secret")
        click.echo("🧹 Removed shared Cognito secret")
        
        if os.path.exists("gateway.config"):
            os.remove("gateway.config")
            click.echo("🧹 Removed gateway.config file")
        
        click.echo(f"\n🎉 Deleted {success_count} gateway(s) successfully")
    else:
        click.echo("\n❌ No gateways were deleted", err=True)
        sys.exit(1)


@cli.command()
@click.option("--name", required=True, help="Name for the gateway (e.g., healthcare-basic-gw)")
@click.option(
    "--tier",
    type=click.Choice(["basic", "premium"], case_sensitive=False),
    default="basic",
    help="Tier level for the gateway (basic or premium)",
)
@click.option(
    "--api-spec-file",
    default="prerequisite/lambda/api_spec.json",
    help="Path to the API specification file (default: prerequisite/lambda/api_spec.json)",
)
def create(name, tier, api_spec_file):
    """Create a new AgentCore gateway for healthcare clinical document processing.
    
    Examples:
        # Create basic tier gateway
        python agentcore_gateway.py create --name healthcare-basic-gw --tier basic
        
        # Create premium tier gateway with custom API spec
        python agentcore_gateway.py create --name healthcare-premium-gw --tier premium --api-spec-file custom_spec.json
    """
    click.echo(f"🚀 Creating Healthcare AgentCore gateway: {name}")
    click.echo(f"📍 Region: {REGION}")
    click.echo(f"🏥 Tier: {tier}")

    # Validate API spec file exists
    if not os.path.exists(api_spec_file):
        click.echo(f"❌ API specification file not found: {api_spec_file}", err=True)
        sys.exit(1)

    try:
        api_spec = load_api_spec(api_spec_file)
        gateway = create_gateway(gateway_name=name, api_spec=api_spec, tier=tier)
        click.echo(f"🎉 Gateway created successfully with ID: {gateway['id']}")
        click.echo(f"🔗 Gateway URL: {gateway['gateway_url']}")

    except Exception as e:
        click.echo(f"❌ Failed to create gateway: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.option(
    "--gateway-id",
    help="Gateway ID to delete (if not provided, will read from SSM parameters)",
)
@click.option(
    "--tier",
    type=click.Choice(["basic", "premium"], case_sensitive=False),
    help="Tier level (required if gateway-id not provided)",
)
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
def delete(gateway_id, tier, confirm):
    """Delete an AgentCore gateway and all its targets.
    
    Examples:
        # Delete basic tier gateway
        python agentcore_gateway.py delete --tier basic --confirm
        
        # Delete specific gateway by ID
        python agentcore_gateway.py delete --gateway-id gw-abc123 --confirm
    """

    # If no gateway ID provided, try to read from config
    if not gateway_id:
        if not tier:
            click.echo(
                "❌ Either --gateway-id or --tier must be provided",
                err=True,
            )
            sys.exit(1)
            
        gateway_id = get_gateway_id_from_config(tier)
        if not gateway_id:
            click.echo(
                f"❌ No gateway ID found in SSM parameters for tier: {tier}",
                err=True,
            )
            sys.exit(1)
        click.echo(f"📖 Using gateway ID from SSM (tier: {tier}): {gateway_id}")

    # Confirmation prompt
    if not confirm:
        if not click.confirm(
            f"⚠️  Are you sure you want to delete gateway {gateway_id}? This action cannot be undone."
        ):
            click.echo("❌ Operation cancelled")
            sys.exit(0)

    click.echo(f"🗑️  Deleting gateway: {gateway_id}")

    if delete_gateway(gateway_id):
        click.echo("✅ Gateway deleted successfully")

        # Clean up SSM parameters for the specified tier
        if tier:
            delete_ssm_parameter(f"/app/healthcare/agentcore/{tier}_gateway_id")
            delete_ssm_parameter(f"/app/healthcare/agentcore/{tier}_gateway_name")
            delete_ssm_parameter(f"/app/healthcare/agentcore/{tier}_gateway_arn")
            delete_ssm_parameter(f"/app/healthcare/agentcore/{tier}_gateway_url")
            click.echo(f"🧹 Removed {tier} tier gateway SSM parameters")
        
        # Only delete shared cognito secret if both tiers are gone
        try:
            basic_gw = get_gateway_id_from_config("basic")
            premium_gw = get_gateway_id_from_config("premium")
            if not basic_gw and not premium_gw:
                delete_ssm_parameter("/app/healthcare/agentcore/cognito_secret")
                click.echo("🧹 Removed shared Cognito secret")
        except:
            pass

        # Clean up config file if it exists (backward compatibility)
        if os.path.exists("gateway.config"):
            os.remove("gateway.config")
            click.echo("🧹 Removed gateway.config file")

        click.echo("🎉 Gateway and configuration deleted successfully")
    else:
        click.echo("❌ Failed to delete gateway", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()
