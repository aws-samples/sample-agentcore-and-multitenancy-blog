#!/usr/bin/python
# Copyright 2026 Amazon.com and its affiliates; all rights reserved.
# SPDX-License-Identifier: MIT-0

"""
Registry Publisher: Creates the Agent Registry and publishes MCP gateway records.

This script is invoked by deploy.sh after gateways are created and before agents
are configured. It ensures the Agent Registry exists, publishes records for both
basic and premium tiers, and stores the registry ID in SSM Parameter Store.
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

from utils import get_aws_region, get_ssm_parameter, put_ssm_parameter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

REGION = get_aws_region()

REGISTRY_NAME = "healthcare-mcp-registry"
REGISTRY_ID_SSM_PATH = "/app/healthcare/agentcore/registry_id"

TIER_CONFIGS = [
    {
        "tier": "basic",
        "record_name": "healthcare-mcp-gateway-basic",
        "description": "Healthcare Lambda Gateway - Basic Tier",
        "gateway_url_ssm": "/app/healthcare/agentcore/basic_gateway_url",
    },
    {
        "tier": "premium",
        "record_name": "healthcare-mcp-gateway-premium",
        "description": "Healthcare Lambda Gateway - Premium Tier",
        "gateway_url_ssm": "/app/healthcare/agentcore/premium_gateway_url",
    },
]


def create_or_get_registry(client, registry_name: str) -> str:
    """
    Create the Agent Registry if it doesn't exist, wait for READY state.

    Attempts to create a new registry with the given name. If a ConflictException
    is raised (registry already exists), lists registries and finds the existing ID.
    Polls the registry status up to 120 seconds waiting for it to reach READY state.

    Args:
        client: boto3 client for bedrock-agent-core-control.
        registry_name: Name for the registry resource.

    Returns:
        The registry ID.

    Raises:
        SystemExit: If creation fails or registry doesn't reach READY in 120s.
    """
    registry_id = None

    try:
        logger.info(f"Creating registry '{registry_name}'...")
        response = client.create_registry(registryName=registry_name)
        registry_id = response["registryId"]
        logger.info(f"Registry creation initiated. ID: {registry_id}")
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        if error_code == "ConflictException":
            logger.info(f"Registry '{registry_name}' already exists. Finding existing ID...")
            registry_id = _find_existing_registry(client, registry_name)
            if not registry_id:
                logger.error(
                    f"Registry '{registry_name}' reported as existing but could not be found."
                )
                sys.exit(1)
            logger.info(f"Found existing registry ID: {registry_id}")
        else:
            logger.error(f"Failed to create registry '{registry_name}': {e}")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to create registry '{registry_name}': {e}")
        sys.exit(1)

    # Poll for READY state up to 120 seconds
    if not _wait_for_registry_ready(client, registry_id, max_wait_seconds=120):
        logger.error(
            f"Registry '{registry_id}' did not reach READY state within 120 seconds."
        )
        sys.exit(1)

    return registry_id


def _find_existing_registry(client, registry_name: str) -> str | None:
    """List registries and find the one matching the given name.

    Args:
        client: boto3 client for bedrock-agent-core-control.
        registry_name: Name of the registry to find.

    Returns:
        The registry ID if found, None otherwise.
    """
    try:
        response = client.list_registries()
        registries = response.get("registries", [])
        for registry in registries:
            if registry.get("registryName") == registry_name:
                return registry.get("registryId")
    except Exception as e:
        logger.error(f"Failed to list registries: {e}")
    return None


def _wait_for_registry_ready(client, registry_id: str, max_wait_seconds: int = 120) -> bool:
    """Poll registry status until it reaches READY state.

    Args:
        client: boto3 client for bedrock-agent-core-control.
        registry_id: The registry ID to check.
        max_wait_seconds: Maximum time to wait in seconds.

    Returns:
        True if registry reached READY state, False if timeout or error.
    """
    logger.info(f"Waiting for registry '{registry_id}' to reach READY state...")
    start_time = time.time()

    while time.time() - start_time < max_wait_seconds:
        try:
            response = client.get_registry(registryId=registry_id)
            status = response.get("status", "")

            if status == "READY":
                logger.info(f"Registry '{registry_id}' is READY.")
                return True
            elif status in ("FAILED", "DELETING"):
                logger.error(f"Registry '{registry_id}' entered '{status}' state.")
                return False
            else:
                # Still creating or updating, wait and retry
                time.sleep(5)
        except Exception as e:
            logger.error(f"Error checking registry status: {e}")
            return False

    return False


def publish_record(client, registry_id: str, tier: str, gateway_url: str,
                   record_name: str, description: str) -> None:
    """
    Publish or update a registry record for the given tier.

    Creates a registry record with descriptorType="MCP" and inlineContent JSON
    containing tier, endpoint_url, and updated_at (ISO 8601 UTC). If the record
    already exists (ConflictException), updates the existing record instead.

    Args:
        client: boto3 client for bedrock-agent-core-control.
        registry_id: The Agent Registry ID.
        tier: The tier identifier ("basic" or "premium").
        gateway_url: The MCP gateway HTTPS URL.
        record_name: The name for the registry record.
        description: The description for the registry record.

    Raises:
        SystemExit: If record publishing fails.
    """
    inline_content = json.dumps({
        "tier": tier,
        "endpoint_url": gateway_url,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    })

    descriptors = {
        "mcp": {
            "server": {
                "inlineContent": inline_content,
            }
        }
    }

    try:
        logger.info(f"Publishing registry record '{record_name}' for tier '{tier}'...")
        client.create_registry_record(
            registryId=registry_id,
            recordName=record_name,
            description=description,
            descriptorType="MCP",
            descriptors=descriptors,
        )
        logger.info(f"Successfully published record '{record_name}'.")
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        if error_code == "ConflictException":
            logger.info(
                f"Record '{record_name}' already exists. Updating..."
            )
            try:
                client.update_registry_record(
                    registryId=registry_id,
                    recordName=record_name,
                    description=description,
                    descriptorType="MCP",
                    descriptors=descriptors,
                )
                logger.info(f"Successfully updated record '{record_name}'.")
            except Exception as update_error:
                logger.error(
                    f"Failed to update registry record for tier '{tier}': {update_error}"
                )
                sys.exit(1)
        else:
            logger.error(
                f"Failed to publish registry record for tier '{tier}': {e}"
            )
            sys.exit(1)
    except Exception as e:
        logger.error(
            f"Failed to publish registry record for tier '{tier}': {e}"
        )
        sys.exit(1)


def main():
    """CLI entrypoint: create registry and publish both tier records.

    Reads gateway URLs from SSM Parameter Store, creates or finds the Agent Registry,
    publishes records for basic and premium tiers, and stores the registry ID in SSM.
    """
    logger.info("Starting Agent Registry publishing...")

    # Create the bedrock-agent-core-control client
    client = boto3.client("bedrock-agent-core-control", region_name=REGION)

    # Read gateway URLs from SSM for each tier
    tier_urls = {}
    for tier_config in TIER_CONFIGS:
        tier = tier_config["tier"]
        ssm_path = tier_config["gateway_url_ssm"]
        try:
            url = get_ssm_parameter(ssm_path)
            tier_urls[tier] = url
            logger.info(f"Retrieved gateway URL for tier '{tier}' from SSM: {url}")
        except Exception as e:
            logger.error(
                f"Failed to read gateway URL from SSM parameter '{ssm_path}' "
                f"for tier '{tier}': {e}"
            )
            sys.exit(1)

    # Create or get the Agent Registry
    registry_id = create_or_get_registry(client, REGISTRY_NAME)

    # Publish records for each tier
    for tier_config in TIER_CONFIGS:
        tier = tier_config["tier"]
        gateway_url = tier_urls[tier]
        publish_record(
            client=client,
            registry_id=registry_id,
            tier=tier,
            gateway_url=gateway_url,
            record_name=tier_config["record_name"],
            description=tier_config["description"],
        )

    # Store registry ID as SSM parameter
    try:
        put_ssm_parameter(REGISTRY_ID_SSM_PATH, registry_id)
        logger.info(
            f"Stored registry ID '{registry_id}' in SSM at '{REGISTRY_ID_SSM_PATH}'."
        )
    except Exception as e:
        logger.error(f"Failed to store registry ID in SSM: {e}")
        sys.exit(1)

    logger.info("Agent Registry publishing completed successfully.")


if __name__ == "__main__":
    main()
