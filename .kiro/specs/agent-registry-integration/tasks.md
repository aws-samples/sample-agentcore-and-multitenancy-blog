# Implementation Plan: Agent Registry Integration

## Overview

This plan implements dynamic MCP gateway endpoint discovery from the AWS Agent Registry, replacing direct SSM parameter lookups. The implementation introduces a `DiscoveryClient` module with process-lifetime caching and SSM fallback, a `RegistryPublisher` deployment script, and integrates the new discovery flow into the existing `HealthcareAgent` initialization.

## Tasks

- [x] 1. Create DiscoveryClient module with core resolution logic
  - [x] 1.1 Create `agent/discovery_client.py` with DiscoveryClient class, class-level cache, `__init__`, `resolve`, and `clear_cache` methods
    - Implement `__init__` accepting optional `region` parameter (defaults to `AWS_REGION` env var or `"us-east-1"`)
    - Implement `resolve(tier)` that checks TIER_CONFIG validity, checks class-level cache, queries Agent Registry via `boto3` `bedrock_agentcore` client's `list_registry_records`, filters/selects records by tier and most recent `updated_at`, caches successful registry results, and falls back to SSM on failure
    - Implement `clear_cache()` classmethod to reset the class-level `_cache` dict
    - Use 5-second timeout for registry API calls (`read_timeout=5, connect_timeout=5` in boto3 Config)
    - Parse registry record `inlineContent` JSON to extract `tier`, `endpoint_url`, and `updated_at` fields
    - Validate records: skip any missing `tier`, `endpoint_url`, or `updated_at`; skip if `endpoint_url` doesn't start with `https://` or exceeds 2048 chars; skip if `tier` is not `"basic"` or `"premium"`
    - Select record with most recent `updated_at` among tier-matching records; if tied, select first in list
    - On registry failure (timeout, HTTP error, AccessDenied, credential issues): log warning/error with appropriate detail (role ARN for access denied), fall back to SSM via `get_ssm_parameter`
    - On both registry and SSM failure: raise `RuntimeError` including tier name, registry failure reason, and SSM failure reason
    - On invalid tier (not in TIER_CONFIG): raise `ValueError` immediately without making API calls
    - Only cache results from successful registry lookups; never cache SSM fallback results
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3, 3.4, 4.5, 6.3, 6.4, 7.1, 7.2, 7.3_

  - [ ]* 1.2 Write property test for record selection (Property 1)
    - **Property 1: Record selection picks most recent matching record**
    - Generate lists of registry records with random tiers and timestamps using hypothesis
    - Assert that `DiscoveryClient` returns `endpoint_url` from the record with most recent `updated_at` among tier-matching records
    - Assert that ties are broken by selecting the first record in the list
    - **Validates: Requirements 1.2, 1.3**

  - [ ]* 1.3 Write property test for invalid record skipping (Property 2)
    - **Property 2: Invalid records are skipped during selection**
    - Generate records with random field omissions (missing tier, endpoint_url, or updated_at)
    - Generate records with invalid values (tier not basic/premium, URL not starting with https://, URL > 2048 chars)
    - Assert that invalid records are excluded and only valid records are considered for selection
    - **Validates: Requirements 4.1, 4.2, 4.4, 4.5**

  - [ ]* 1.4 Write property test for dual-failure error message (Property 3)
    - **Property 3: Dual-failure error message includes all diagnostic information**
    - Generate random tier name, registry failure reason, and SSM failure reason strings
    - Assert that the raised `RuntimeError` message contains all three values
    - **Validates: Requirements 2.2**

  - [ ]* 1.5 Write property test for fallback warning log (Property 4)
    - **Property 4: Fallback warning log includes tier, reason, and path**
    - Generate random tier name, registry failure reason, and SSM parameter path strings
    - Assert that the warning log message contains all three values
    - **Validates: Requirements 2.3**

  - [ ]* 1.6 Write property test for caching behavior (Property 5)
    - **Property 5: Successful registry resolution is cached and reused**
    - Generate random tier and gateway URL, mock registry to return a record
    - Call `resolve()` twice for the same tier and assert second call returns same URL without making an API call
    - **Validates: Requirements 7.1, 7.2**

  - [ ]* 1.7 Write property test for fallback not cached (Property 6)
    - **Property 6: Fallback results are never cached**
    - Generate random tier, mock registry to fail (triggering SSM fallback)
    - Assert cache does not contain an entry for that tier after fallback resolution
    - Assert subsequent `resolve()` call re-attempts the Agent Registry lookup
    - **Validates: Requirements 7.3, 7.4, 7.5**

- [x] 2. Checkpoint - Verify DiscoveryClient module
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Create RegistryPublisher deployment script
  - [x] 3.1 Create `scripts/registry_publisher.py` with `create_or_get_registry`, `publish_record`, and `main` functions
    - Implement `create_or_get_registry(client, registry_name)`: attempt `create_registry` with name `"healthcare-mcp-registry"`; if `ConflictException`, list registries and find existing ID; poll for READY state up to 120 seconds; exit non-zero with error log if creation fails or timeout exceeded
    - Implement `publish_record(client, registry_id, tier, gateway_url)`: create a registry record with `descriptorType="MCP"` and `inlineContent` JSON containing `tier`, `endpoint_url`, and `updated_at` (ISO 8601 UTC); if `ConflictException`, update existing record; exit non-zero with error log if publishing fails
    - Implement `main()`: read gateway URLs from SSM at `/app/healthcare/agentcore/{tier}_gateway_url` for both basic and premium; call `create_or_get_registry`; call `publish_record` for each tier; store registry ID as SSM parameter at `/app/healthcare/agentcore/registry_id`
    - Use record names `"healthcare-mcp-gateway-basic"` and `"healthcare-mcp-gateway-premium"`
    - Use descriptions `"Healthcare Lambda Gateway - Basic Tier"` and `"Healthcare Lambda Gateway - Premium Tier"`
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8_

  - [ ]* 3.2 Write unit tests for RegistryPublisher
    - Test happy path: creates registry, publishes 2 records, stores SSM parameter
    - Test registry already exists (ConflictException): skips creation, proceeds to publish
    - Test record already exists (ConflictException): updates record instead of creating duplicate
    - Test registry creation timeout (>120s): exits non-zero with error log
    - Test record publish failure: exits non-zero, logs which tier failed
    - Test SSM read failure for gateway URL: exits non-zero with error log
    - _Requirements: 5.2, 5.3, 5.4, 5.5, 5.7, 5.8_

- [x] 4. Integrate DiscoveryClient into HealthcareAgent initialization
  - [x] 4.1 Modify `agent/agent.py` to use DiscoveryClient for gateway URL resolution
    - Replace `gateway_url = get_ssm_parameter(config["gateway_url_ssm"])` with `DiscoveryClient().resolve(tier)`
    - Add import: `from .discovery_client import DiscoveryClient`
    - Ensure the resolved URL is passed to `MCPClient` with the same bearer token and headers (X-Tier, X-Clinic-ID, X-S3-Prefix) as before
    - No changes to TIER_CONFIG, MCPClient initialization pattern, or downstream tool registration
    - _Requirements: 6.1, 6.2, 6.5_

  - [ ]* 4.2 Write unit tests for HealthcareAgent initialization with DiscoveryClient
    - Test that HealthcareAgent uses DiscoveryClient.resolve() instead of direct SSM call for gateway URL
    - Test that HealthcareAgent raises RuntimeError if DiscoveryClient fails to resolve
    - Test that headers and bearer token are still correctly passed to MCPClient
    - _Requirements: 6.1, 6.2, 6.5_

- [x] 5. Update deploy.sh to invoke RegistryPublisher
  - [x] 5.1 Add registry publishing step to `deploy.sh` after gateway creation and before agent configuration
    - Add `print_step "Publishing MCP gateway records to Agent Registry..."` followed by `python scripts/registry_publisher.py`
    - Place the new step after the `agentcore_gateway.py create-all` step and before the `agentcore configure` steps
    - Ensure the script exits on failure (existing `set -e` handles this)
    - _Requirements: 5.1_

- [x] 6. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties using `hypothesis` with `@settings(max_examples=100)`
- Unit tests validate specific examples and edge cases using `pytest` with mocked boto3 clients
- The `DiscoveryClient` is designed as a standalone module importable independently for testing
- The only change to existing production code is in `agent/agent.py` (one import + one line replacement)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "1.4", "1.5", "1.6", "1.7", "3.1"] },
    { "id": 2, "tasks": ["3.2", "4.1", "5.1"] },
    { "id": 3, "tasks": ["4.2"] }
  ]
}
```
