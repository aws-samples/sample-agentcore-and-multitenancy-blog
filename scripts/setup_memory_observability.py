#!/usr/bin/python
# Copyright 2026 Amazon.com and its affiliates; all rights reserved.
# SPDX-License-Identifier: MIT-0

"""
AgentCore Memory Observability Setup Script

This script enables observability for AgentCore Memory resources to enable
cost tracking and tenant attribution in the healthcare multi-tenancy system.

Memory observability is NOT automatic - it must be configured manually by:
1. Creating CloudWatch log groups for memory logs
2. Creating delivery sources (APPLICATION_LOGS, TRACES)
3. Creating delivery destinations (CloudWatch Logs, X-Ray)
4. Creating deliveries to connect sources to destinations

Once enabled, OpenTelemetry baggage (tier, clinic_id) will be captured
in CloudWatch Logs, enabling per-clinic cost queries.

Usage:
    # Enable observability for both memory resources
    python setup_memory_observability.py enable-all
    
    # Enable observability for specific memory
    python setup_memory_observability.py enable --memory-id mem-abc123
    
    # Enable observability for tier
    python setup_memory_observability.py enable --tier basic
    
    # Verify observability status
    python setup_memory_observability.py verify --tier basic
"""

import click
import boto3
import sys
import time
from botocore.exceptions import ClientError
from utils import get_aws_region

# AWS clients
REGION = get_aws_region()
logs_client = boto3.client("logs", region_name=REGION)
sts_client = boto3.client("sts", region_name=REGION)
ssm_client = boto3.client("ssm", region_name=REGION)

# Get AWS account ID
ACCOUNT_ID = sts_client.get_caller_identity()["Account"]


def get_memory_id_from_ssm(tier: str) -> str:
    """Retrieve memory ID from SSM parameter store."""
    param_name = f"/app/healthcare/memory/{tier}_id"
    try:
        response = ssm_client.get_parameter(Name=param_name)
        return response["Parameter"]["Value"]
    except ClientError as e:
        raise click.ClickException(
            f"❌ Could not retrieve memory ID from SSM ({param_name}): {e}"
        )


def create_log_group(log_group_name: str) -> str:
    """Create CloudWatch log group for memory logs."""
    try:
        logs_client.create_log_group(logGroupName=log_group_name)
        click.echo(f"✅ Created log group: {log_group_name}")
    except logs_client.exceptions.ResourceAlreadyExistsException:
        click.echo(f"ℹ️  Log group already exists: {log_group_name}")
    except Exception as e:
        raise click.ClickException(f"❌ Failed to create log group: {e}")
    
    # Return log group ARN
    return f"arn:aws:logs:{REGION}:{ACCOUNT_ID}:log-group:{log_group_name}"


def create_delivery_source(name: str, log_type: str, resource_arn: str) -> dict:
    """Create delivery source for logs or traces."""
    try:
        response = logs_client.put_delivery_source(
            name=name,
            logType=log_type,
            resourceArn=resource_arn
        )
        click.echo(f"✅ Created delivery source: {name} ({log_type})")
        return response["deliverySource"]
    except logs_client.exceptions.ResourceAlreadyExistsException:
        click.echo(f"ℹ️  Delivery source already exists: {name}")
        # Get existing delivery source
        response = logs_client.get_delivery_source(name=name)
        return response["deliverySource"]
    except Exception as e:
        raise click.ClickException(f"❌ Failed to create delivery source: {e}")


def create_delivery_destination(name: str, destination_type: str, destination_arn: str = None) -> dict:
    """Create delivery destination for CloudWatch Logs or X-Ray."""
    try:
        params = {
            "name": name,
            "deliveryDestinationType": destination_type
        }
        
        # CloudWatch Logs requires destination ARN
        if destination_type == "CWL" and destination_arn:
            params["deliveryDestinationConfiguration"] = {
                "destinationResourceArn": destination_arn
            }
        
        response = logs_client.put_delivery_destination(**params)
        click.echo(f"✅ Created delivery destination: {name} ({destination_type})")
        return response["deliveryDestination"]
    except logs_client.exceptions.ResourceAlreadyExistsException:
        click.echo(f"ℹ️  Delivery destination already exists: {name}")
        # Get existing delivery destination
        response = logs_client.get_delivery_destination(name=name)
        return response["deliveryDestination"]
    except Exception as e:
        raise click.ClickException(f"❌ Failed to create delivery destination: {e}")


def ensure_xray_cloudwatch_logs_destination() -> None:
    """
    Ensure X-Ray trace segment destination includes CloudWatch Logs.
    
    AWS requires CloudWatch Logs to be enabled as a trace segment destination
    before X-Ray delivery destinations can be used with CloudWatch Logs deliveries.
    See: https://docs.aws.amazon.com/xray/latest/api/API_UpdateTraceSegmentDestination.html
    """
    try:
        xray_client = boto3.client("xray", region_name=REGION)
        xray_client.update_trace_segment_destination(Destination="CloudWatchLogs")
        click.echo("✅ Enabled CloudWatch Logs as X-Ray trace segment destination")
    except ClientError as e:
        # If already enabled or not supported, log and continue
        error_code = e.response["Error"]["Code"]
        if error_code == "InvalidRequestException":
            click.echo("ℹ️  CloudWatch Logs already enabled as X-Ray trace segment destination")
        else:
            click.echo(f"⚠️  Could not update X-Ray trace segment destination: {e}")
            click.echo("   Traces delivery to X-Ray may fail. This is non-blocking.")


def create_delivery(source_name: str, destination_arn: str) -> dict:
    """Create delivery to connect source to destination."""
    try:
        response = logs_client.create_delivery(
            deliverySourceName=source_name,
            deliveryDestinationArn=destination_arn
        )
        click.echo(f"✅ Created delivery: {source_name} → {destination_arn}")
        return response["delivery"]
    except logs_client.exceptions.ResourceAlreadyExistsException:
        click.echo(f"ℹ️  Delivery already exists for source: {source_name}")
        # List deliveries to find existing one
        deliveries = logs_client.describe_deliveries()
        for delivery in deliveries.get("deliveries", []):
            if delivery.get("deliverySourceName") == source_name:
                return delivery
        return None
    except Exception as e:
        raise click.ClickException(f"❌ Failed to create delivery: {e}")


def enable_memory_observability(memory_id: str, tier: str = None) -> dict:
    """
    Enable observability for AgentCore Memory resource.
    
    This configures:
    1. CloudWatch log group for APPLICATION_LOGS
    2. Delivery source for logs
    3. Delivery source for traces
    4. Delivery destination for CloudWatch Logs
    5. Delivery destination for X-Ray
    6. Deliveries to connect sources to destinations
    
    Args:
        memory_id: AgentCore Memory resource ID
        tier: Optional tier name for display purposes
    
    Returns:
        dict: Configuration details including log group name and delivery IDs
    """
    click.echo(f"\n{'='*60}")
    click.echo(f"🔍 Enabling Observability for Memory: {memory_id}")
    if tier:
        click.echo(f"🏥 Tier: {tier}")
    click.echo(f"📍 Region: {REGION}")
    click.echo(f"🔢 Account: {ACCOUNT_ID}")
    click.echo(f"{'='*60}\n")
    
    # Memory resource ARN
    memory_arn = f"arn:aws:bedrock-agentcore:{REGION}:{ACCOUNT_ID}:memory/{memory_id}"
    
    # Step 1: Create log group for memory logs
    click.echo("📝 Step 1: Creating CloudWatch log group...")
    log_group_name = f"/aws/vendedlogs/bedrock-agentcore/memory/APPLICATION_LOGS/{memory_id}"
    log_group_arn = create_log_group(log_group_name)
    
    # Step 2: Create delivery source for logs
    click.echo("\n📤 Step 2: Creating delivery source for APPLICATION_LOGS...")
    logs_source = create_delivery_source(
        name=f"{memory_id}-logs-source",
        log_type="APPLICATION_LOGS",
        resource_arn=memory_arn
    )
    
    # Step 3: Create delivery source for traces
    click.echo("\n📤 Step 3: Creating delivery source for TRACES...")
    traces_source = create_delivery_source(
        name=f"{memory_id}-traces-source",
        log_type="TRACES",
        resource_arn=memory_arn
    )
    
    # Step 4: Create delivery destination for CloudWatch Logs
    click.echo("\n📥 Step 4: Creating delivery destination for CloudWatch Logs...")
    logs_destination = create_delivery_destination(
        name=f"{memory_id}-logs-destination",
        destination_type="CWL",
        destination_arn=log_group_arn
    )
    
    # Step 5: Enable CloudWatch Logs as X-Ray trace segment destination (prerequisite)
    click.echo("\n🔧 Step 5: Ensuring X-Ray trace segment destination is configured...")
    ensure_xray_cloudwatch_logs_destination()
    
    # Step 5b: Create delivery destination for X-Ray
    click.echo("\n📥 Step 5b: Creating delivery destination for X-Ray...")
    traces_destination = create_delivery_destination(
        name=f"{memory_id}-traces-destination",
        destination_type="XRAY"
    )
    
    # Step 6: Create deliveries (connect sources to destinations)
    click.echo("\n🔗 Step 6: Creating deliveries...")
    logs_delivery = create_delivery(
        source_name=logs_source["name"],
        destination_arn=logs_destination["arn"]
    )
    
    # Traces delivery is best-effort — X-Ray config issues should not block deployment
    traces_delivery = None
    try:
        traces_delivery = create_delivery(
            source_name=traces_source["name"],
            destination_arn=traces_destination["arn"]
        )
    except Exception as e:
        click.echo(f"⚠️  Traces delivery to X-Ray failed (non-blocking): {e}")
        click.echo("   Logs delivery is active. Traces can be configured later.")
    
    # Summary
    result = {
        "memory_id": memory_id,
        "log_group_name": log_group_name,
        "logs_delivery_id": logs_delivery.get("id") if logs_delivery else None,
        "traces_delivery_id": traces_delivery.get("id") if traces_delivery else None,
    }
    
    click.echo(f"\n{'='*60}")
    click.echo(f"✅ Observability enabled for Memory: {memory_id}")
    click.echo(f"{'='*60}")
    click.echo(f"📊 Log Group: {log_group_name}")
    click.echo(f"🔗 Logs Delivery: {result['logs_delivery_id']}")
    click.echo(f"🔗 Traces Delivery: {result['traces_delivery_id']}")
    click.echo(f"\n💡 Tenant context (baggage) will now be captured in CloudWatch Logs")
    click.echo(f"   Query example: fields @timestamp, tier, eventCount")
    
    return result


def verify_observability(memory_id: str, tier: str = None) -> bool:
    """
    Verify that observability is properly configured for a memory resource.
    
    Checks:
    1. Log group exists
    2. Delivery sources exist
    3. Delivery destinations exist
    4. Deliveries are active
    
    Args:
        memory_id: AgentCore Memory resource ID
        tier: Optional tier name for display purposes
    
    Returns:
        bool: True if observability is fully configured, False otherwise
    """
    click.echo(f"\n{'='*60}")
    click.echo(f"🔍 Verifying Observability for Memory: {memory_id}")
    if tier:
        click.echo(f"🏥 Tier: {tier}")
    click.echo(f"{'='*60}\n")
    
    checks_passed = 0
    checks_total = 4
    
    # Check 1: Log group exists
    log_group_name = f"/aws/vendedlogs/bedrock-agentcore/memory/APPLICATION_LOGS/{memory_id}"
    try:
        logs_client.describe_log_groups(logGroupNamePrefix=log_group_name, limit=1)
        click.echo(f"✅ Check 1/4: Log group exists: {log_group_name}")
        checks_passed += 1
    except Exception as e:
        click.echo(f"❌ Check 1/4: Log group not found: {log_group_name}")
    
    # Check 2: Delivery sources exist
    try:
        logs_client.get_delivery_source(name=f"{memory_id}-logs-source")
        logs_client.get_delivery_source(name=f"{memory_id}-traces-source")
        click.echo(f"✅ Check 2/4: Delivery sources exist (logs and traces)")
        checks_passed += 1
    except Exception as e:
        click.echo(f"❌ Check 2/4: Delivery sources not found")
    
    # Check 3: Delivery destinations exist
    try:
        logs_client.get_delivery_destination(name=f"{memory_id}-logs-destination")
        logs_client.get_delivery_destination(name=f"{memory_id}-traces-destination")
        click.echo(f"✅ Check 3/4: Delivery destinations exist (CloudWatch Logs and X-Ray)")
        checks_passed += 1
    except Exception as e:
        click.echo(f"❌ Check 3/4: Delivery destinations not found")
    
    # Check 4: Deliveries are active
    try:
        deliveries = logs_client.describe_deliveries()
        active_deliveries = [
            d for d in deliveries.get("deliveries", [])
            if d.get("deliverySourceName", "").startswith(memory_id)
        ]
        if len(active_deliveries) >= 2:
            click.echo(f"✅ Check 4/4: Deliveries are active ({len(active_deliveries)} found)")
            checks_passed += 1
        else:
            click.echo(f"❌ Check 4/4: Expected 2 deliveries, found {len(active_deliveries)}")
    except Exception as e:
        click.echo(f"❌ Check 4/4: Could not verify deliveries")
    
    # Summary
    click.echo(f"\n{'='*60}")
    if checks_passed == checks_total:
        click.echo(f"✅ Observability fully configured: {checks_passed}/{checks_total} checks passed")
        click.echo(f"{'='*60}")
        return True
    else:
        click.echo(f"⚠️  Observability partially configured: {checks_passed}/{checks_total} checks passed")
        click.echo(f"{'='*60}")
        return False


@click.group()
def cli():
    """AgentCore Memory Observability Setup for Healthcare Multi-Tenancy.
    
    Enable observability for AgentCore Memory resources to track costs per clinic.
    This is required for tenant attribution and cost allocation.
    """
    pass


@cli.command()
@click.option(
    "--memory-id",
    help="Memory ID to enable observability for",
)
@click.option(
    "--tier",
    type=click.Choice(["basic", "premium"], case_sensitive=False),
    help="Tier level (will read memory ID from SSM if provided)",
)
def enable(memory_id, tier):
    """Enable observability for a specific memory resource.
    
    Examples:
        # Enable for basic tier (reads memory ID from SSM)
        python setup_memory_observability.py enable --tier basic
        
        # Enable for specific memory ID
        python setup_memory_observability.py enable --memory-id mem-abc123
    """
    if not memory_id and not tier:
        click.echo("❌ Either --memory-id or --tier must be provided", err=True)
        sys.exit(1)
    
    # Get memory ID from SSM if tier provided
    if tier and not memory_id:
        memory_id = get_memory_id_from_ssm(tier)
        click.echo(f"📖 Using memory ID from SSM: {memory_id}")
    
    try:
        enable_memory_observability(memory_id, tier)
        click.echo("\n🎉 Observability setup completed successfully!")
    except Exception as e:
        click.echo(f"\n❌ Failed to enable observability: {e}", err=True)
        sys.exit(1)


@cli.command()
def enable_all():
    """Enable observability for both basic and premium tier memory resources.
    
    This is a convenience command that enables observability for:
    - healthcare-basic-memory
    - healthcare-premium-memory
    
    Example:
        python setup_memory_observability.py enable-all
    """
    click.echo("🚀 Enabling observability for both Healthcare memory resources")
    click.echo(f"📍 Region: {REGION}")
    click.echo(f"🔢 Account: {ACCOUNT_ID}\n")
    
    success_count = 0
    
    # Enable for basic tier
    try:
        memory_id = get_memory_id_from_ssm("basic")
        enable_memory_observability(memory_id, "basic")
        success_count += 1
    except Exception as e:
        click.echo(f"\n⚠️  Failed to enable observability for basic tier: {e}")
    
    # Enable for premium tier
    try:
        memory_id = get_memory_id_from_ssm("premium")
        enable_memory_observability(memory_id, "premium")
        success_count += 1
    except Exception as e:
        click.echo(f"\n⚠️  Failed to enable observability for premium tier: {e}")
    
    # Summary
    click.echo(f"\n{'='*60}")
    if success_count == 2:
        click.echo("🎉 Observability enabled for both memory resources!")
    elif success_count == 1:
        click.echo("⚠️  Observability enabled for 1 of 2 memory resources")
    else:
        click.echo("❌ Failed to enable observability for any memory resources")
        sys.exit(1)
    click.echo(f"{'='*60}")
    
    click.echo("\n💡 Next steps:")
    click.echo("   1. Generate test traffic to populate logs")
    click.echo("   2. Query CloudWatch Logs Insights for per-clinic costs")


@cli.command()
@click.option(
    "--memory-id",
    help="Memory ID to verify observability for",
)
@click.option(
    "--tier",
    type=click.Choice(["basic", "premium"], case_sensitive=False),
    help="Tier level (will read memory ID from SSM if provided)",
)
def verify(memory_id, tier):
    """Verify observability configuration for a memory resource.
    
    Examples:
        # Verify basic tier
        python setup_memory_observability.py verify --tier basic
        
        # Verify specific memory ID
        python setup_memory_observability.py verify --memory-id mem-abc123
    """
    if not memory_id and not tier:
        click.echo("❌ Either --memory-id or --tier must be provided", err=True)
        sys.exit(1)
    
    # Get memory ID from SSM if tier provided
    if tier and not memory_id:
        memory_id = get_memory_id_from_ssm(tier)
        click.echo(f"📖 Using memory ID from SSM: {memory_id}")
    
    try:
        is_configured = verify_observability(memory_id, tier)
        if not is_configured:
            sys.exit(1)
    except Exception as e:
        click.echo(f"\n❌ Verification failed: {e}", err=True)
        sys.exit(1)


@cli.command()
def verify_all():
    """Verify observability configuration for both memory resources.
    
    Example:
        python setup_memory_observability.py verify-all
    """
    click.echo("🔍 Verifying observability for both Healthcare memory resources\n")
    
    success_count = 0
    
    # Verify basic tier
    try:
        memory_id = get_memory_id_from_ssm("basic")
        if verify_observability(memory_id, "basic"):
            success_count += 1
    except Exception as e:
        click.echo(f"\n⚠️  Failed to verify basic tier: {e}")
    
    # Verify premium tier
    try:
        memory_id = get_memory_id_from_ssm("premium")
        if verify_observability(memory_id, "premium"):
            success_count += 1
    except Exception as e:
        click.echo(f"\n⚠️  Failed to verify premium tier: {e}")
    
    # Summary
    click.echo(f"\n{'='*60}")
    if success_count == 2:
        click.echo("✅ Observability fully configured for both memory resources!")
    elif success_count == 1:
        click.echo("⚠️  Observability configured for 1 of 2 memory resources")
    else:
        click.echo("❌ Observability not configured for any memory resources")
        sys.exit(1)
    click.echo(f"{'='*60}")


if __name__ == "__main__":
    cli()
