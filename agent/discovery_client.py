# Copyright 2026 Amazon.com and its affiliates; all rights reserved.
# SPDX-License-Identifier: MIT-0

"""
Discovery client for resolving MCP gateway endpoints from the AWS Agent Registry.

The DiscoveryClient queries the Agent Registry for records matching a given tier,
caches successful registry lookups for process lifetime, and falls back to SSM
Parameter Store when the registry is unavailable.
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

from .utils import get_ssm_parameter

logger = logging.getLogger(__name__)


def _get_tier_config():
    """Late import of TIER_CONFIG to avoid circular imports with agent.py."""
    from .agent import TIER_CONFIG
    return TIER_CONFIG

# SSM path where the Agent Registry ID is stored
REGISTRY_ID_SSM_PATH = "/app/healthcare/agentcore/registry_id"


class DiscoveryClient:
    """Resolves MCP gateway URLs from the Agent Registry with SSM fallback.

    Successful registry lookups are cached at the class level (process-lifetime).
    Fallback results from SSM are never cached so subsequent calls re-attempt the registry.
    """

    _cache: dict = {}

    def __init__(self, region: str | None = None):
        """
        Args:
            region: AWS region. Defaults to AWS_REGION env var or "us-east-1".
        """
        self._region = region or os.environ.get("AWS_REGION", "us-east-1")
        self._client = boto3.client(
            "bedrock-agent-core-control",
            region_name=self._region,
            config=Config(
                read_timeout=5,
                connect_timeout=5,
            ),
        )

    def resolve(self, tier: str) -> str:
        """
        Resolve the MCP gateway URL for the given tier.

        Args:
            tier: One of the tiers defined in TIER_CONFIG ("basic" or "premium").

        Returns:
            A fully-qualified HTTPS URL string.

        Raises:
            ValueError: If tier is not in TIER_CONFIG.
            RuntimeError: If both registry and SSM lookups fail.
        """
        # Validate tier immediately without making API calls
        tier_config = _get_tier_config()
        if tier not in tier_config:
            raise ValueError(
                f"Invalid tier '{tier}'. Must be one of: {list(tier_config.keys())}"
            )

        # Check class-level cache
        if tier in DiscoveryClient._cache:
            return DiscoveryClient._cache[tier]

        # Attempt registry lookup
        registry_failure_reason = None
        try:
            url = self._query_registry(tier)
            if url:
                # Cache successful registry result
                DiscoveryClient._cache[tier] = url
                return url
            # No matching records found — treat as registry failure for fallback
            registry_failure_reason = f"No matching registry records found for tier '{tier}'"
        except (ReadTimeoutError, ConnectTimeoutError) as e:
            registry_failure_reason = f"Registry timeout: {e}"
            logger.warning(
                f"Agent Registry timeout for tier '{tier}': {e}. "
                f"Falling back to SSM parameter: {tier_config[tier]['gateway_url_ssm']}"
            )
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code in ("AccessDeniedException", "AccessDenied"):
                # Log role ARN for access denied
                role_arn = self._get_role_arn()
                registry_failure_reason = (
                    f"AccessDenied: Role '{role_arn}' lacks permission to query the Agent Registry"
                )
                logger.error(
                    f"Agent Registry access denied for tier '{tier}': "
                    f"Role '{role_arn}' lacks permission. "
                    f"Falling back to SSM parameter: {tier_config[tier]['gateway_url_ssm']}"
                )
            else:
                registry_failure_reason = f"Registry ClientError ({error_code}): {e}"
                logger.warning(
                    f"Agent Registry error for tier '{tier}': {e}. "
                    f"Falling back to SSM parameter: {tier_config[tier]['gateway_url_ssm']}"
                )
        except (NoCredentialsError, CredentialRetrievalError) as e:
            registry_failure_reason = f"Credential failure: {e}"
            logger.error(
                f"Agent Registry credential failure for tier '{tier}': {e}. "
                f"Falling back to SSM parameter: {tier_config[tier]['gateway_url_ssm']}"
            )
        except Exception as e:
            registry_failure_reason = f"Unexpected registry error: {e}"
            logger.warning(
                f"Agent Registry unexpected error for tier '{tier}': {e}. "
                f"Falling back to SSM parameter: {tier_config[tier]['gateway_url_ssm']}"
            )

        # If we reach here, log the fallback warning (if not already logged above with specific detail)
        if registry_failure_reason and "Falling back" not in (registry_failure_reason or ""):
            logger.warning(
                f"Agent Registry lookup failed for tier '{tier}': {registry_failure_reason}. "
                f"Falling back to SSM parameter: {tier_config[tier]['gateway_url_ssm']}"
            )

        # Fallback to SSM
        ssm_path = tier_config[tier]["gateway_url_ssm"]
        try:
            url = get_ssm_parameter(ssm_path)
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

        Returns:
            The endpoint URL from the best matching record, or None if no valid matches.
        """
        # Read registry ID from SSM
        registry_id = get_ssm_parameter(REGISTRY_ID_SSM_PATH)

        # Query registry records
        response = self._client.list_registry_records(registryId=registry_id)
        records = response.get("registryRecords", [])

        # Parse and filter records
        valid_records = []
        for record in records:
            parsed = self._parse_record(record)
            if parsed is None:
                continue
            record_tier, endpoint_url, updated_at = parsed
            if record_tier == tier:
                valid_records.append((endpoint_url, updated_at))

        if not valid_records:
            return None

        # Select the record with the most recent updated_at
        # If tied, select first in list (stable sort preserves original order)
        best_url = max(valid_records, key=lambda r: r[1])[0]

        # Handle ties: find the max timestamp, then pick the first record with that timestamp
        max_timestamp = max(r[1] for r in valid_records)
        for endpoint_url, updated_at in valid_records:
            if updated_at == max_timestamp:
                return endpoint_url

        return best_url

    def _parse_record(self, record: dict) -> tuple | None:
        """Parse a registry record and validate its fields.

        Returns:
            A tuple of (tier, endpoint_url, updated_at) if valid, or None if invalid.
        """
        record_id = record.get("recordId", record.get("name", "unknown"))

        try:
            # Navigate to inlineContent
            descriptors = record.get("descriptors", {})
            mcp = descriptors.get("mcp", {})
            server = mcp.get("server", {})
            inline_content_str = server.get("inlineContent", "")

            if not inline_content_str:
                logger.warning(
                    f"Registry record '{record_id}' has no inlineContent, skipping."
                )
                return None

            content = json.loads(inline_content_str)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(
                f"Registry record '{record_id}' has invalid inlineContent JSON: {e}, skipping."
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
        if tier not in ("basic", "premium"):
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

    def _get_role_arn(self) -> str:
        """Retrieve the current IAM role ARN for error logging."""
        try:
            sts = boto3.client("sts", region_name=self._region)
            identity = sts.get_caller_identity()
            return identity.get("Arn", "unknown")
        except Exception:
            return "unknown"

    @classmethod
    def clear_cache(cls) -> None:
        """Clear all cached registry results across all tiers."""
        cls._cache = {}
