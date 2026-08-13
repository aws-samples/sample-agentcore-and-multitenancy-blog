#!/usr/bin/python
# Copyright 2026 Amazon.com and its affiliates; all rights reserved.
# SPDX-License-Identifier: MIT-0

"""
Registry Publisher: Creates the Agent Registry and publishes MCP gateway records.

This script is invoked by deploy.sh after gateways are created and before agents
are configured. It ensures the Agent Registry exists, publishes records for both
basic and premium tiers, and stores the registry ID in SSM Parameter Store.

Uses the agent-registry-control client (new namespace as of Aug 2026).
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

from utils import get_aws_region, get_ssm_parameter, put_ssm_parameter, REGISTRY_ID_SSM_PATH

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

REGION = get_aws_region()

REGISTRY_NAME = "healthcare-mcp-registry"

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


def _registry_id_from_arn(arn: str) -> str:
    """Extract the registry ID from an ARN like arn:aws:agent-registry:region:account:registry/ID."""
    return arn.rsplit("/", 1)[-1]


def create_or_get_registry(client, registry_name: str) -> str:
    """
    Create the Agent Registry if it doesn't exist, wait for READY state.

    Returns:
        The registry ID.

    Raises:
        SystemExit: If creation fails or registry doesn't reach READY in 120s.
    """
    registry_id = None

    try:
        logger.info(f"Creating registry '{registry_name}'...")
        response = client.create_registry(name=registry_name)
        registry_arn = response["registryArn"]
        registry_id = _registry_id_from_arn(registry_arn)
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
    """List registries and find the one matching the given name."""
    try:
        response = client.list_registries()
        registries = response.get("registries", [])
        for registry in registries:
            if registry.get("name") == registry_name:
                return registry.get("registryId")
    except Exception as e:
        logger.error(f"Failed to list registries: {e}")
    return None


def _wait_for_registry_ready(client, registry_id: str, max_wait_seconds: int = 120) -> bool:
    """Poll registry status until it reaches READY state."""
    logger.info(f"Waiting for registry '{registry_id}' to reach READY state...")
    start_time = time.time()

    while time.time() - start_time < max_wait_seconds:
        try:
            response = client.get_registry(registryId=registry_id)
            status = response.get("status", "")

            if status == "READY":
                logger.info(f"Registry '{registry_id}' is READY.")
                return True
            elif status in ("CREATE_FAILED", "DELETE_FAILED", "DELETING"):
                logger.error(f"Registry '{registry_id}' entered '{status}' state.")
                return False
            else:
                time.sleep(5)
        except Exception as e:
            logger.error(f"Error checking registry status: {e}")
            return False

    return False


def _find_existing_record(client, registry_id: str, record_name: str) -> str | None:
    """Find an existing record by name and return its recordId."""
    try:
        response = client.list_registry_records(
            registryId=registry_id,
            filters=[{"name": "name", "values": [record_name]}],
        )
        records = response.get("registryRecords", [])
        for record in records:
            if record.get("name") == record_name:
                return record.get("recordId")
    except Exception as e:
        logger.warning(f"Failed to search for existing record '{record_name}': {e}")
    return None


def publish_record(client, registry_id: str, tier: str, gateway_url: str,
                   record_name: str, description: str) -> None:
    """
    Publish or update a registry record for the given tier.

    Uses the new agent-registry schema: recordType="MCP", descriptors.mcpServer.data
    contains a JSON string with tier, endpoint_url, and updated_at.

    Raises:
        SystemExit: If record publishing fails.
    """
    record_data = json.dumps({
        "tier": tier,
        "endpoint_url": gateway_url,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    })

    descriptors = {
        "custom": {
            "data": record_data,
        }
    }

    try:
        logger.info(f"Publishing registry record '{record_name}' for tier '{tier}'...")
        client.create_registry_record(
            registryId=registry_id,
            name=record_name,
            description=description,
            recordType="CUSTOM",
            descriptors=descriptors,
        )
        logger.info(f"Successfully published record '{record_name}'.")
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        if error_code == "ConflictException":
            logger.info(f"Record '{record_name}' already exists. Updating...")
            try:
                record_id = _find_existing_record(client, registry_id, record_name)
                if not record_id:
                    logger.error(f"Could not find existing record '{record_name}' to update.")
                    sys.exit(1)
                client.update_registry_record(
                    registryId=registry_id,
                    recordId=record_id,
                    name=record_name,
                    description={"optionalValue": description},
                    recordType="CUSTOM",
                    descriptors={"optionalValue": {"custom": {"optionalValue": {"data": {"optionalValue": record_data}}}}},
                )
                logger.info(f"Successfully updated record '{record_name}'.")
            except Exception as update_error:
                logger.error(
                    f"Failed to update registry record for tier '{tier}': {update_error}"
                )
                sys.exit(1)
        else:
            logger.error(f"Failed to publish registry record for tier '{tier}': {e}")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to publish registry record for tier '{tier}': {e}")
        sys.exit(1)


def _submit_records_for_approval(client, registry_id: str) -> None:
    """Submit all DRAFT records for approval (auto-approval will approve them).

    Waits briefly for records to transition from CREATING to DRAFT.
    """
    import time
    # Wait for records to finish creating
    time.sleep(5)

    try:
        response = client.list_registry_records(registryId=registry_id)
        records = response.get("registryRecords", [])
        for record in records:
            if record.get("status") == "DRAFT":
                record_id = record.get("recordId")
                record_name = record.get("name", record_id)
                try:
                    client.submit_registry_record_for_approval(
                        registryId=registry_id, recordId=record_id
                    )
                    logger.info(f"Submitted record '{record_name}' for approval.")
                except ClientError as e:
                    logger.warning(f"Could not submit record '{record_name}' for approval: {e}")
            elif record.get("status") == "CREATING":
                logger.info(f"Record '{record.get('name')}' still creating, waiting...")
                time.sleep(5)
                # Retry this record
                try:
                    client.submit_registry_record_for_approval(
                        registryId=registry_id, recordId=record.get("recordId")
                    )
                    logger.info(f"Submitted record '{record.get('name')}' for approval.")
                except ClientError as e:
                    logger.warning(f"Could not submit record '{record.get('name')}' for approval: {e}")
    except Exception as e:
        logger.warning(f"Could not submit records for approval: {e}")


def main():
    """CLI entrypoint: create registry and publish both tier records."""
    logger.info("Starting Agent Registry publishing...")

    client = boto3.client("agent-registry-control", region_name=REGION)

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

    # Ensure auto-approval is enabled so records become discoverable immediately
    try:
        client.update_registry(
            registryId=registry_id,
            name=REGISTRY_NAME,
            approvalConfiguration={"optionalValue": {"autoApprovalRules": ["APPROVE_ALL"]}},
        )
        logger.info("Registry auto-approval enabled.")
        # Wait for registry to return to READY after update
        _wait_for_registry_ready(client, registry_id, max_wait_seconds=120)
    except ClientError as e:
        logger.warning(f"Could not set auto-approval (may already be set): {e}")

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

    # Submit records for approval (auto-approval will approve them immediately)
    _submit_records_for_approval(client, registry_id)

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
