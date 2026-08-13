# Copyright 2026 Amazon.com and its affiliates; all rights reserved.
# SPDX-License-Identifier: MIT-0

"""
Discovery client for resolving MCP gateway endpoints from the AWS Agent Registry.

The DiscoveryClient queries the Agent Registry for records matching a given tier,
caches successful registry lookups for process lifetime, and falls back to SSM
Parameter Store when the registry is unavailable.

Uses the agent-registry data plane client (new namespace as of Aug 2026).
"""

import json
import logging
import os
from datetime import datetime, timezone

import boto3
from botocore.config import Config
from botocore.exceptions import (
    ClientError,
    NoCredentialsError,
    ReadTimeoutError,
    ConnectTimeoutError,
    CredentialRetrievalError,
)

from .utils import get_ssm_parameter, REGISTRY_ID_SSM_PATH

logger = logging.getLogger(__name__)

# Valid tier identifiers for registry record filtering
VALID_TIERS = ("basic", "premium")


class DiscoveryClient:
    """Resolves MCP gateway URLs from the Agent Registry with SSM fallback.

    Successful registry lookups are cached at the class level (process-lifetime).
    Fallback results from SSM are never cached so subsequent calls re-attempt the registry.
    """

    _cache: dict = {}
    _client = None
    _client_region: str | None = None

    def __init__(self, region: str | None = None):
        """
        Args:
            region: AWS region. Defaults to AWS_REGION env var or "us-east-1".
        """
        self._region = region or os.environ.get("AWS_REGION", "us-east-1")

        # Reuse a class-level boto3 client if region matches
        if DiscoveryClient._client is None or DiscoveryClient._client_region != self._region:
            DiscoveryClient._client = boto3.client(
                "agent-registry",
                region_name=self._region,
                config=Config(
                    read_timeout=5,
                    connect_timeout=5,
                ),
            )
            DiscoveryClient._client_region = self._region

    def resolve(self, tier: str, fallback_ssm_path: str) -> str:
        """
        Resolve the MCP gateway URL for the given tier.

        Args:
            tier: Service tier identifier ("basic" or "premium").
            fallback_ssm_path: SSM parameter path for the gateway URL, used as
                fallback when the registry is unavailable.

        Returns:
            A fully-qualified HTTPS URL string.

        Raises:
            ValueError: If tier is not a valid tier identifier.
            RuntimeError: If both registry and SSM lookups fail.
        """
        if tier not in VALID_TIERS:
            raise ValueError(
                f"Invalid tier '{tier}'. Must be one of: {list(VALID_TIERS)}"
            )

        # Check class-level cache
        if tier in DiscoveryClient._cache:
            return DiscoveryClient._cache[tier]

        # Attempt registry lookup
        registry_failure_reason = None
        try:
            url = self._query_registry(tier)
            if url:
                DiscoveryClient._cache[tier] = url
                return url
            registry_failure_reason = f"No matching registry records found for tier '{tier}'"
        except (ReadTimeoutError, ConnectTimeoutError) as e:
            registry_failure_reason = f"Registry timeout: {e}"
            logger.warning(
                f"Agent Registry timeout for tier '{tier}': {e}. "
                f"Falling back to SSM parameter: {fallback_ssm_path}"
            )
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code in ("AccessDeniedException", "AccessDenied"):
                registry_failure_reason = f"AccessDenied: {e}"
                logger.error(
                    f"Agent Registry access denied for tier '{tier}': {e}. "
                    f"Falling back to SSM parameter: {fallback_ssm_path}"
                )
            else:
                registry_failure_reason = f"Registry ClientError ({error_code}): {e}"
                logger.warning(
                    f"Agent Registry error for tier '{tier}': {e}. "
                    f"Falling back to SSM parameter: {fallback_ssm_path}"
                )
        except (NoCredentialsError, CredentialRetrievalError) as e:
            registry_failure_reason = f"Credential failure: {e}"
            logger.error(
                f"Agent Registry credential failure for tier '{tier}': {e}. "
                f"Falling back to SSM parameter: {fallback_ssm_path}"
            )
        except Exception as e:
            registry_failure_reason = f"Unexpected registry error: {e}"
            logger.warning(
                f"Agent Registry unexpected error for tier '{tier}': {e}. "
                f"Falling back to SSM parameter: {fallback_ssm_path}"
            )

        # If we reach here, log the fallback warning (if not already logged above)
        if registry_failure_reason and "Falling back" not in (registry_failure_reason or ""):
            logger.warning(
                f"Agent Registry lookup failed for tier '{tier}': {registry_failure_reason}. "
                f"Falling back to SSM parameter: {fallback_ssm_path}"
            )

        # Fallback to SSM
        try:
            url = get_ssm_parameter(fallback_ssm_path)
            # Do NOT cache SSM fallback results
            return url
        except Exception as ssm_error:
            raise RuntimeError(
                f"Failed to resolve gateway URL for tier '{tier}'. "
                f"Registry failure: {registry_failure_reason}. "
                f"SSM failure: {ssm_error}"
            )

    def _query_registry(self, tier: str) -> str | None:
        """Query the Agent Registry for records matching the given tier.

        Uses the agent-registry data plane: list records, then batch_get for
        full details including descriptors.

        Returns:
            The endpoint URL from the best matching record, or None if no valid matches.

        Raises:
            RuntimeError: If the registry ID cannot be read from SSM.
        """
        try:
            registry_id = get_ssm_parameter(REGISTRY_ID_SSM_PATH)
        except Exception as e:
            raise RuntimeError(
                f"Registry ID not found in SSM at '{REGISTRY_ID_SSM_PATH}'. "
                f"Has the registry been published via registry_publisher.py? Error: {e}"
            )

        # List record summaries
        response = DiscoveryClient._client.list_discoverable_registry_records(
            registryId=registry_id
        )
        record_summaries = response.get("registryRecords", [])

        if not record_summaries:
            return None

        # Get full record details (with descriptors) via batch_get
        record_ids = [r["recordId"] for r in record_summaries if "recordId" in r]
        if not record_ids:
            return None

        batch_response = DiscoveryClient._client.batch_get_discoverable_registry_record(
            entries=[{"registryId": registry_id, "recordIds": record_ids}]
        )
        full_records = batch_response.get("registryRecords", [])

        # Parse and filter records
        valid_records = []
        for record in full_records:
            parsed = self._parse_record(record)
            if parsed is None:
                continue
            record_tier, endpoint_url, updated_at = parsed
            if record_tier == tier:
                valid_records.append((endpoint_url, updated_at))

        if not valid_records:
            return None

        # Select the first record with the most recent updated_at (tie-break: list order)
        max_timestamp = max(r[1] for r in valid_records)
        for endpoint_url, updated_at in valid_records:
            if updated_at == max_timestamp:
                return endpoint_url

    def _parse_record(self, record: dict) -> tuple | None:
        """Parse a registry record and validate its fields.

        Expects the agent-registry schema where descriptor data lives at
        descriptors.custom.data (JSON string).

        Returns:
            A tuple of (tier, endpoint_url, updated_at) if valid, or None if invalid.
        """
        record_id = record.get("recordId", record.get("name", "unknown"))

        try:
            descriptors = record.get("descriptors", {})
            custom = descriptors.get("custom", {})
            data_str = custom.get("data", "")

            if not data_str:
                logger.warning(
                    f"Registry record '{record_id}' has no custom.data, skipping."
                )
                return None

            content = json.loads(data_str)
        except (json.JSONDecodeError, TypeError, AttributeError) as e:
            logger.warning(
                f"Registry record '{record_id}' has invalid custom.data JSON: {e}, skipping."
            )
            return None

        # Extract required fields
        tier = content.get("tier")
        endpoint_url = content.get("endpoint_url")
        updated_at_str = content.get("updated_at")

        # Validate presence of required fields
        if not tier:
            logger.warning(
                f"Registry record '{record_id}' is missing 'tier' field, skipping."
            )
            return None
        if not endpoint_url:
            logger.warning(
                f"Registry record '{record_id}' is missing 'endpoint_url' field, skipping."
            )
            return None
        if not updated_at_str:
            logger.warning(
                f"Registry record '{record_id}' is missing 'updated_at' field, skipping."
            )
            return None

        # Validate tier value
        if tier not in VALID_TIERS:
            logger.warning(
                f"Registry record '{record_id}' has invalid tier '{tier}', skipping."
            )
            return None

        # Validate endpoint_url
        if not endpoint_url.startswith("https://"):
            logger.warning(
                f"Registry record '{record_id}' endpoint_url does not start with 'https://', skipping."
            )
            return None
        if len(endpoint_url) > 2048:
            logger.warning(
                f"Registry record '{record_id}' endpoint_url exceeds 2048 characters, skipping."
            )
            return None

        # Parse updated_at timestamp
        try:
            updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError) as e:
            logger.warning(
                f"Registry record '{record_id}' has invalid 'updated_at' timestamp: {e}, skipping."
            )
            return None

        return (tier, endpoint_url, updated_at)

    @classmethod
    def clear_cache(cls) -> None:
        """Clear all cached registry results across all tiers."""
        cls._cache = {}
