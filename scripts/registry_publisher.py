#!/usr/bin/python
# Copyright 2026 Amazon.com and its affiliates; all rights reserved.
# SPDX-License-Identifier: MIT-0

"""Submit CloudFormation-managed Agent Registry records for approval.

CloudFormation creates and updates AWS::AgentRegistry::RegistryRecord resources,
but record submission is a separate lifecycle API operation. The registry stack
enables APPROVE_ALL, so submitting each DRAFT revision makes it discoverable.
"""

import logging
import sys
import time

import boto3

from utils import REGISTRY_ID_SSM_PATH, get_aws_region, get_ssm_parameter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

POLL_SECONDS = 5
TIMEOUT_SECONDS = 180
EXPECTED_RECORD_NAMES = {
    "healthcare-mcp-gateway-basic",
    "healthcare-mcp-gateway-premium",
}
TERMINAL_FAILURE_STATES = {"CREATE_FAILED", "UPDATE_FAILED", "REJECTED", "DEPRECATED"}


def wait_for_records(client, registry_id: str) -> list[dict]:
    """Wait until CloudFormation-created records leave transitional states."""
    deadline = time.time() + TIMEOUT_SECONDS
    while time.time() < deadline:
        response = client.list_registry_records(registryId=registry_id)
        records = response.get("registryRecords", [])
        records_by_name = {r.get("name"): r for r in records}
        missing = EXPECTED_RECORD_NAMES - records_by_name.keys()
        if missing:
            logger.info(
                "Waiting for registry records to appear: %s",
                ", ".join(sorted(missing)),
            )
            time.sleep(POLL_SECONDS)
            continue

        records = [records_by_name[name] for name in sorted(EXPECTED_RECORD_NAMES)]
        failures = [r for r in records if r.get("status") in TERMINAL_FAILURE_STATES]
        if failures:
            states = ", ".join(f"{r.get('name')}={r.get('status')}" for r in failures)
            raise RuntimeError(f"Registry record creation failed: {states}")

        transitional = [
            r for r in records if r.get("status") in {"CREATING", "UPDATING"}
        ]
        if not transitional:
            return records

        states = ", ".join(f"{r.get('name')}={r.get('status')}" for r in transitional)
        logger.info("Waiting for registry records: %s", states)
        time.sleep(POLL_SECONDS)

    raise TimeoutError("Timed out waiting for Agent Registry records")


def submit_drafts(client, registry_id: str, records: list[dict]) -> None:
    """Submit each DRAFT revision and wait for auto-approval."""
    for record in records:
        status = record.get("status")
        name = record.get("name", record.get("recordId", "unknown"))
        if status == "DRAFT":
            logger.info("Submitting registry record '%s' for approval", name)
            client.submit_registry_record_for_approval(
                registryId=registry_id,
                recordId=record["recordId"],
            )
        elif status == "APPROVED":
            logger.info("Registry record '%s' is already approved", name)
        elif status != "PENDING_APPROVAL":
            raise RuntimeError(f"Registry record '{name}' is in unexpected state '{status}'")

    deadline = time.time() + TIMEOUT_SECONDS
    while time.time() < deadline:
        listed = client.list_registry_records(registryId=registry_id).get(
            "registryRecords", []
        )
        current = [r for r in listed if r.get("name") in EXPECTED_RECORD_NAMES]
        failures = [r for r in current if r.get("status") in TERMINAL_FAILURE_STATES]
        if failures:
            states = ", ".join(f"{r.get('name')}={r.get('status')}" for r in failures)
            raise RuntimeError(f"Registry record approval failed: {states}")
        if len(current) == len(EXPECTED_RECORD_NAMES) and all(
            r.get("status") == "APPROVED" for r in current
        ):
            logger.info("All Agent Registry records are approved and discoverable")
            return
        time.sleep(POLL_SECONDS)

    raise TimeoutError("Timed out waiting for Agent Registry record approval")


def main() -> None:
    region = get_aws_region()
    registry_id = get_ssm_parameter(REGISTRY_ID_SSM_PATH)
    client = boto3.client("agent-registry-control", region_name=region)

    logger.info("Submitting records in Agent Registry %s", registry_id)
    records = wait_for_records(client, registry_id)
    submit_drafts(client, registry_id, records)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        logger.error("Agent Registry publication failed: %s", error)
        sys.exit(1)
