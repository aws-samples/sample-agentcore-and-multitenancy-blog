#!/usr/bin/python
# Copyright 2026 Amazon.com and its affiliates; all rights reserved.
# SPDX-License-Identifier: MIT-0

"""
AgentCore Gateway Rate Limiting for Healthcare Multi-Tenancy.

Configures per-user and per-target rate limits on the basic and premium
AgentCore gateways, giving fine-grained control over how much traffic an
individual caller can push through the gateway's tools.

Tenancy model (Option A — identity-based, no Cognito changes):
  - Tier separation is free: basic and premium already have SEPARATE gateways,
    so each tier just gets its own rate numbers (see TIER_RATE_LIMITS).
  - Per-user fairness uses the JWT `sub` claim ($.context.jwt.sub) as the
    dimension key. `sub` is stable, bounded, and always present in the token.
    A wildcard entry gives every distinct user their own isolated bucket.
  - Per-target protection uses `targetName` with a wildcard, so the Lambda tool
    target and the managed-KB target each get their own bucket, preventing one
    tool from starving the other.

Why not per-clinic?
  Clinic identity lives in the Cognito custom attribute `custom:clinic_id`.
  The rate-limit API rejects dimension keys containing a colon (the claim-name
  pattern is `\\$\\.context\\.jwt\\.[a-zA-Z_][a-zA-Z0-9_\\-\\.]{0,61}[a-zA-Z0-9_]`),
  and the pool has no pre-token-generation Lambda to emit a colon-free alias, so
  `custom:clinic_id` is not usable as a dimension key today. To enable per-clinic
  buckets later (Option B), add a pre-token-gen Lambda that copies
  `custom:clinic_id` -> a bare `clinic_id` claim, then set
  `clinic_dimension_enabled = True` below and redeploy. The config is written to
  make that a data-only change.

Rate numbers are derived from the existing API Gateway usage-plan ratios
(basic 2 rps / 50 per day, premium 10 rps / 500 per day — premium is 5x basic):
  - basic  per-user: 120 requests/min + 5  connections/sec   (~2 rps)
  - premium per-user: 600 requests/min + 20 connections/sec   (~10 rps, 5x)
  - basic  per-target catch-all:  2 requests/sec
  - premium per-target catch-all: 10 requests/sec

The gateway also enforces service-managed quotas; the effective limit is the
minimum of the customer-defined limit and the service quota. Rate limits are
fail-open, so they are for traffic management / QoS, NOT a security boundary —
authentication (CUSTOM_JWT), the Cedar policy engine, and API Gateway usage
plans remain the security layers.

Usage:
    python scripts/agentcore_rate_limits.py create              # both tiers
    python scripts/agentcore_rate_limits.py create --tier basic # one tier
    python scripts/agentcore_rate_limits.py status              # show current limits
    python scripts/agentcore_rate_limits.py delete              # remove managed limits
    python scripts/agentcore_rate_limits.py delete --tier premium
"""

import sys

import boto3
import click

from utils import get_aws_region, get_ssm_parameter


REGION = get_aws_region()

gateway_client = boto3.client("bedrock-agentcore-control", region_name=REGION)
logs_client = boto3.client("logs", region_name=REGION)
sts_client = boto3.client("sts", region_name=REGION)

ACCOUNT_ID = sts_client.get_caller_identity()["Account"]

# Marker prefix so we only ever manage rate limits created by this script and
# never touch limits someone configured by hand in the console.
MANAGED_PREFIX = "[healthcare-managed]"

TIERS = ("basic", "premium")

# --- Per-tier rate limit configuration -------------------------------------
# Derived from the API Gateway usage-plan ratios (premium = 5x basic).
# Each tier gets two rate limits on its own gateway:
#   1. per-user  — dimension key $.context.jwt.sub (wildcard => one bucket/user)
#   2. per-target — dimension key targetName (wildcard => one bucket/target)
#
# To enable per-clinic buckets later (Option B), flip clinic_dimension_enabled
# to True after a pre-token-gen Lambda emits a bare `clinic_id` claim. The
# per-user limit then becomes [clinic_id, sub] and a per-clinic ceiling limit
# on [clinic_id] is added. See _build_rate_limits().
CLINIC_DIMENSION_ENABLED = False

TIER_RATE_LIMITS = {
    "basic": {
        "per_user": {
            "requests_per_minute": 120,   # ~2 rps, matches basic usage plan
            "connections_per_second": 5,
        },
        "per_target_requests_per_second": 2,
        # Used only when CLINIC_DIMENSION_ENABLED is True (Option B).
        "per_clinic": {
            "requests_per_minute": 240,
            "connections_per_second": 10,
        },
    },
    "premium": {
        "per_user": {
            "requests_per_minute": 600,   # ~10 rps, 5x basic (premium usage plan)
            "connections_per_second": 20,
        },
        "per_target_requests_per_second": 10,
        "per_clinic": {
            "requests_per_minute": 1200,
            "connections_per_second": 40,
        },
    },
}


def _get_gateway_id(tier: str) -> str:
    """Read the gateway ID for a tier from SSM (written by agentcore_gateway.py)."""
    try:
        return get_ssm_parameter(f"/app/healthcare/agentcore/{tier}_gateway_id")
    except Exception as e:
        click.echo(
            f"❌ Could not read gateway ID for tier '{tier}' from SSM "
            f"(/app/healthcare/agentcore/{tier}_gateway_id): {e}",
            err=True,
        )
        return None


def _build_rate_limits(tier: str) -> list:
    """Build the desired rate-limit definitions for a tier.

    Returns a list of dicts: {name, dimensionKeys, description, entries}.
    `name` is a stable local handle used for logging and matching; the actual
    identity on the gateway is the dimensionKeys set (used for idempotency).
    """
    cfg = TIER_RATE_LIMITS[tier]
    per_user = cfg["per_user"]
    limits = []

    if CLINIC_DIMENSION_ENABLED:
        # Option B: per-clinic ceiling + per-user cap within each clinic.
        # NOTE: requires a bare `clinic_id` JWT claim (pre-token-gen Lambda).
        per_clinic = cfg["per_clinic"]
        limits.append(
            {
                "name": f"{tier}-per-clinic",
                "dimensionKeys": ["$.context.jwt.clinic_id"],
                "description": f"{MANAGED_PREFIX} {tier} per-clinic ceiling",
                "entries": [
                    {
                        "dimensions": {"$.context.jwt.clinic_id": "*"},
                        "requests": [
                            {"rate": per_clinic["requests_per_minute"], "period": "minute"}
                        ],
                        "connections": [
                            {"rate": per_clinic["connections_per_second"], "period": "second"}
                        ],
                    }
                ],
            }
        )
        # Per-user cap scoped within each clinic. Order matters: the catch-all
        # `*` may only appear in trailing positions, so clinic_id precedes sub.
        limits.append(
            {
                "name": f"{tier}-per-user-in-clinic",
                "dimensionKeys": ["$.context.jwt.clinic_id", "$.context.jwt.sub"],
                "description": f"{MANAGED_PREFIX} {tier} per-user cap within clinic",
                "entries": [
                    {
                        "dimensions": {
                            "$.context.jwt.clinic_id": "*",
                            "$.context.jwt.sub": "*",
                        },
                        "requests": [
                            {"rate": per_user["requests_per_minute"], "period": "minute"}
                        ],
                        "connections": [
                            {"rate": per_user["connections_per_second"], "period": "second"}
                        ],
                    }
                ],
            }
        )
    else:
        # Option A (default): per-user fairness via the sub claim.
        limits.append(
            {
                "name": f"{tier}-per-user",
                "dimensionKeys": ["$.context.jwt.sub"],
                "description": f"{MANAGED_PREFIX} {tier} per-user request/connection limit",
                "entries": [
                    {
                        "dimensions": {"$.context.jwt.sub": "*"},
                        "requests": [
                            {"rate": per_user["requests_per_minute"], "period": "minute"}
                        ],
                        "connections": [
                            {"rate": per_user["connections_per_second"], "period": "second"}
                        ],
                    }
                ],
            }
        )

    # Per-target protection (both options): one bucket per downstream target
    # (HealthcareLambda-*, HealthcareKB-*) so one tool cannot starve the other.
    limits.append(
        {
            "name": f"{tier}-per-target",
            "dimensionKeys": ["targetName"],
            "description": f"{MANAGED_PREFIX} {tier} per-target request limit",
            "entries": [
                {
                    "dimensions": {"targetName": "*"},
                    "requests": [
                        {"rate": cfg["per_target_requests_per_second"], "period": "second"}
                    ],
                }
            ],
        }
    )

    return limits


def _list_existing(gateway_id: str) -> list:
    """List all rate limits currently on a gateway (paginated)."""
    items = []
    next_token = None
    while True:
        kwargs = {"gatewayIdentifier": gateway_id, "maxResults": 100}
        if next_token:
            kwargs["nextToken"] = next_token
        resp = gateway_client.list_gateway_rate_limits(**kwargs)
        items.extend(resp.get("rateLimits", []))
        next_token = resp.get("nextToken")
        if not next_token:
            break
    return items


def _find_by_dimension_keys(existing: list, dimension_keys: list) -> dict:
    """Find an existing rate limit whose dimensionKeys match exactly (order-sensitive).

    dimensionKeys order is significant to the gateway (wildcards are trailing-only),
    so we match on the ordered list rather than a set.
    """
    for rl in existing:
        if rl.get("dimensionKeys") == dimension_keys:
            return rl
    return None


def create_rate_limits(tier: str) -> bool:
    """Create or update the managed rate limits for a single tier (idempotent)."""
    gateway_id = _get_gateway_id(tier)
    if not gateway_id:
        return False

    click.echo(f"\n{'='*60}")
    click.echo(f"Configuring rate limits — {tier.title()} tier")
    click.echo(f"Gateway: {gateway_id}")
    click.echo(f"{'='*60}")

    try:
        existing = _list_existing(gateway_id)
    except Exception as e:
        click.echo(f"❌ Could not list existing rate limits: {e}", err=True)
        return False

    desired = _build_rate_limits(tier)
    ok = True

    for spec in desired:
        match = _find_by_dimension_keys(existing, spec["dimensionKeys"])
        try:
            if match:
                rate_limit_id = match["rateLimitId"]
                # dimensionKeys are immutable; update description + entries.
                gateway_client.update_gateway_rate_limit(
                    gatewayIdentifier=gateway_id,
                    rateLimitId=rate_limit_id,
                    description=spec["description"],
                    entries=spec["entries"],
                )
                click.echo(
                    f"♻️  Updated {spec['name']} "
                    f"(dimensionKeys={spec['dimensionKeys']}, id={rate_limit_id})"
                )
            else:
                resp = gateway_client.create_gateway_rate_limit(
                    gatewayIdentifier=gateway_id,
                    dimensionKeys=spec["dimensionKeys"],
                    description=spec["description"],
                    entries=spec["entries"],
                )
                click.echo(
                    f"✅ Created {spec['name']} "
                    f"(dimensionKeys={spec['dimensionKeys']}, id={resp['rateLimitId']})"
                )
        except Exception as e:
            click.echo(f"❌ Failed to apply {spec['name']}: {e}", err=True)
            ok = False

    return ok


def delete_rate_limits(tier: str) -> bool:
    """Delete only the rate limits this script manages (matched by description prefix)."""
    gateway_id = _get_gateway_id(tier)
    if not gateway_id:
        return False

    click.echo(f"\n🗑️  Removing managed rate limits — {tier.title()} tier ({gateway_id})")
    try:
        existing = _list_existing(gateway_id)
    except Exception as e:
        click.echo(f"❌ Could not list existing rate limits: {e}", err=True)
        return False

    managed = [
        rl for rl in existing if (rl.get("description") or "").startswith(MANAGED_PREFIX)
    ]
    if not managed:
        click.echo("ℹ️  No managed rate limits found")
        return True

    ok = True
    for rl in managed:
        rate_limit_id = rl["rateLimitId"]
        try:
            gateway_client.delete_gateway_rate_limit(
                gatewayIdentifier=gateway_id, rateLimitId=rate_limit_id
            )
            click.echo(f"✅ Deleted {rate_limit_id} ({rl.get('description')})")
        except Exception as e:
            click.echo(f"❌ Failed to delete {rate_limit_id}: {e}", err=True)
            ok = False
    return ok


def show_status(tier: str) -> None:
    """Print all rate limits on a tier's gateway (managed and unmanaged)."""
    gateway_id = _get_gateway_id(tier)
    if not gateway_id:
        return

    click.echo(f"\n{'='*60}")
    click.echo(f"Rate limits — {tier.title()} tier ({gateway_id})")
    click.echo(f"{'='*60}")
    try:
        existing = _list_existing(gateway_id)
    except Exception as e:
        click.echo(f"❌ Could not list rate limits: {e}", err=True)
        return

    if not existing:
        click.echo("  (none configured)")
        return

    for rl in existing:
        managed = "★" if (rl.get("description") or "").startswith(MANAGED_PREFIX) else " "
        click.echo(
            f"  {managed} {rl.get('rateLimitId')}  "
            f"keys={rl.get('dimensionKeys')}  status={rl.get('status')}"
        )
        click.echo(f"      {rl.get('description')}")
        for entry in rl.get("entries", []):
            parts = []
            for metric in ("requests", "connections", "tokens"):
                for limit in entry.get(metric, []):
                    parts.append(f"{limit['rate']}/{limit['period']} {metric}")
            click.echo(f"        dims={entry.get('dimensions')} -> {', '.join(parts)}")
    click.echo("\n  ★ = managed by this script")


# --- Application logs (rate-limit observability) ---------------------------
# The gateway emits OpenTelemetry span attributes for every request where
# customer rate limits are evaluated (which bucket matched, whether the request
# was allowed or denied, remaining budget). Those land in the gateway's
# APPLICATION_LOGS delivery. This mirrors the CloudWatch Logs delivery pattern
# used for memory observability (scripts/setup_memory_observability.py).


def _gateway_arn(tier: str) -> str:
    """Read the gateway ARN for a tier from SSM (written by agentcore_gateway.py)."""
    try:
        return get_ssm_parameter(f"/app/healthcare/agentcore/{tier}_gateway_arn")
    except Exception as e:
        click.echo(
            f"❌ Could not read gateway ARN for tier '{tier}' from SSM "
            f"(/app/healthcare/agentcore/{tier}_gateway_arn): {e}",
            err=True,
        )
        return None


def _ensure_log_group(log_group_name: str) -> str:
    """Create the CloudWatch log group if absent; return its ARN."""
    try:
        logs_client.create_log_group(logGroupName=log_group_name)
        click.echo(f"✅ Created log group: {log_group_name}")
    except logs_client.exceptions.ResourceAlreadyExistsException:
        click.echo(f"ℹ️  Log group already exists: {log_group_name}")
    return f"arn:aws:logs:{REGION}:{ACCOUNT_ID}:log-group:{log_group_name}"


def _ensure_delivery_source(name: str, resource_arn: str) -> None:
    """Create the APPLICATION_LOGS delivery source for the gateway if absent."""
    try:
        logs_client.put_delivery_source(
            name=name, logType="APPLICATION_LOGS", resourceArn=resource_arn
        )
        click.echo(f"✅ Created delivery source: {name} (APPLICATION_LOGS)")
    except logs_client.exceptions.ResourceAlreadyExistsException:
        click.echo(f"ℹ️  Delivery source already exists: {name}")


def _ensure_delivery_destination(name: str, log_group_arn: str) -> str:
    """Create the CloudWatch Logs delivery destination if absent; return its ARN."""
    try:
        resp = logs_client.put_delivery_destination(
            name=name,
            deliveryDestinationType="CWL",
            deliveryDestinationConfiguration={"destinationResourceArn": log_group_arn},
        )
        click.echo(f"✅ Created delivery destination: {name} (CWL)")
    except logs_client.exceptions.ResourceAlreadyExistsException:
        click.echo(f"ℹ️  Delivery destination already exists: {name}")
        resp = logs_client.get_delivery_destination(name=name)
    return resp["deliveryDestination"]["arn"]


def _ensure_delivery(source_name: str, destination_arn: str) -> None:
    """Connect the delivery source to the destination if not already linked."""
    try:
        logs_client.create_delivery(
            deliverySourceName=source_name, deliveryDestinationArn=destination_arn
        )
        click.echo(f"✅ Created delivery: {source_name} → CloudWatch Logs")
    except logs_client.exceptions.ResourceAlreadyExistsException:
        click.echo(f"ℹ️  Delivery already exists for source: {source_name}")


def enable_logs(tier: str) -> bool:
    """Enable APPLICATION_LOGS delivery to CloudWatch for a tier's gateway (idempotent)."""
    gateway_id = _get_gateway_id(tier)
    gateway_arn = _gateway_arn(tier)
    if not gateway_id or not gateway_arn:
        return False

    click.echo(f"\n{'='*60}")
    click.echo(f"Enabling gateway application logs — {tier.title()} tier")
    click.echo(f"Gateway: {gateway_id}")
    click.echo(f"{'='*60}")

    try:
        log_group_name = (
            f"/aws/vendedlogs/bedrock-agentcore/gateway/APPLICATION_LOGS/{gateway_id}"
        )
        log_group_arn = _ensure_log_group(log_group_name)

        source_name = f"{gateway_id}-logs-source"
        destination_name = f"{gateway_id}-logs-dest"

        _ensure_delivery_source(source_name, gateway_arn)
        destination_arn = _ensure_delivery_destination(destination_name, log_group_arn)
        _ensure_delivery(source_name, destination_arn)

        click.echo(f"📊 Rate-limit evaluations will appear in: {log_group_name}")
        return True
    except Exception as e:
        click.echo(f"❌ Failed to enable gateway logs for {tier}: {e}", err=True)
        return False


# --- CLI -------------------------------------------------------------------


@click.group()
def cli():
    """Manage AgentCore Gateway rate limits for the healthcare tiers."""
    pass


def _resolve_tiers(tier: str) -> list:
    if tier:
        if tier not in TIERS:
            click.echo(f"❌ Unknown tier '{tier}'. Choose from: {', '.join(TIERS)}", err=True)
            sys.exit(1)
        return [tier]
    return list(TIERS)


@cli.command()
@click.option("--tier", type=click.Choice(TIERS), default=None,
              help="Configure a single tier (default: both).")
@click.option("--skip-logs", is_flag=True,
              help="Skip enabling gateway application logs (rate limits only).")
def create(tier, skip_logs):
    """Create or update rate limits (idempotent), and enable gateway app logs."""
    click.echo("🚦 Configuring AgentCore Gateway rate limits")
    click.echo(f"📍 Region: {REGION}")
    if CLINIC_DIMENSION_ENABLED:
        click.echo("🔧 Clinic dimension: ENABLED (per-clinic + per-user-in-clinic)")
    else:
        click.echo("🔧 Clinic dimension: disabled (per-user via sub + per-target)")

    tiers = _resolve_tiers(tier)
    failures = [t for t in tiers if not create_rate_limits(t)]

    # Application logs give visibility into which bucket allowed/denied each
    # request. Non-fatal: a logging failure should not fail the whole step.
    if not skip_logs:
        for t in tiers:
            try:
                enable_logs(t)
            except Exception as e:
                click.echo(f"⚠️  Could not enable gateway logs for {t} (non-blocking): {e}")

    click.echo(f"\n{'='*60}")
    if failures:
        click.echo(f"❌ Rate limit configuration failed for: {', '.join(failures)}", err=True)
        sys.exit(1)
    click.echo("🎉 Rate limits configured successfully")


@cli.command(name="enable-logs")
@click.option("--tier", type=click.Choice(TIERS), default=None,
              help="Enable logs for a single tier (default: both).")
def enable_logs_cmd(tier):
    """Enable gateway application-log delivery to CloudWatch (rate-limit observability)."""
    failures = [t for t in _resolve_tiers(tier) if not enable_logs(t)]
    if failures:
        click.echo(f"❌ Enabling logs failed for: {', '.join(failures)}", err=True)
        sys.exit(1)
    click.echo("\n🎉 Gateway application logs enabled")


@cli.command()
@click.option("--tier", type=click.Choice(TIERS), default=None,
              help="Show a single tier (default: both).")
def status(tier):
    """Show the rate limits currently configured on the gateways."""
    for t in _resolve_tiers(tier):
        show_status(t)


@cli.command()
@click.option("--tier", type=click.Choice(TIERS), default=None,
              help="Delete a single tier (default: both).")
@click.option("--confirm", is_flag=True, help="Skip the confirmation prompt.")
def delete(tier, confirm):
    """Delete the rate limits managed by this script."""
    tiers = _resolve_tiers(tier)
    if not confirm:
        if not click.confirm(
            f"⚠️  Delete managed rate limits for tier(s) [{', '.join(tiers)}]?"
        ):
            click.echo("❌ Operation cancelled")
            sys.exit(0)

    failures = [t for t in tiers if not delete_rate_limits(t)]
    if failures:
        click.echo(f"❌ Deletion failed for: {', '.join(failures)}", err=True)
        sys.exit(1)
    click.echo("\n🎉 Managed rate limits removed")


if __name__ == "__main__":
    cli()
