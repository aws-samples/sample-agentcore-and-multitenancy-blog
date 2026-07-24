# Requirements Document

## Introduction

This feature replaces the hardcoded SSM parameter-based MCP gateway endpoint discovery in the multi-tenant healthcare agent with dynamic discovery from the AWS Agent Registry. At agent initialization, the system queries the Agent Registry for MCP server records matching the tenant's service tier (basic or premium), connects to the discovered endpoints, and falls back to SSM-based URLs if the registry is unavailable. A deployment script creates the registry and publishes gateway records as part of the existing deploy.sh workflow.

## Glossary

- **Agent_Registry**: An AWS Agent Registry resource used to store and discover MCP server endpoint records for the healthcare agent system.
- **Registry_Record**: A single entry in the Agent Registry describing an MCP server endpoint, including its URL, tier affiliation, and metadata.
- **Discovery_Client**: The module within the healthcare agent responsible for querying the Agent Registry and returning resolved MCP gateway URLs.
- **Tier**: The service level assigned to a tenant — either "basic" or "premium" — which determines which MCP gateway endpoints are available.
- **MCP_Gateway**: A Streamable HTTP endpoint that exposes Lambda-backed tools (patient_context, clinic_config) via the Model Context Protocol.
- **SSM_Parameter**: An AWS Systems Manager Parameter Store entry containing a gateway URL, used as the current discovery mechanism and fallback source.
- **Deployment_Script**: The shell script (deploy.sh) that orchestrates infrastructure provisioning and agent deployment.
- **Registry_Publisher**: The script component that creates the Agent Registry and publishes MCP gateway records during deployment.

## Requirements

### Requirement 1: Registry-Based Endpoint Discovery

**User Story:** As a healthcare agent, I want to discover MCP gateway endpoints from the Agent Registry at initialization, so that endpoint configuration is centrally managed and dynamically resolvable without code changes.

#### Acceptance Criteria

1. WHEN the HealthcareAgent is initialized, THE Discovery_Client SHALL query the Agent Registry for Registry_Records matching the requested Tier within 5 seconds.
2. WHEN the Agent Registry returns one or more matching Registry_Records, THE Discovery_Client SHALL return the MCP gateway URL from the matching record.
3. WHEN multiple Registry_Records match the requested Tier, THE Discovery_Client SHALL select the record with the most recent update timestamp. IF two or more records share the same most recent timestamp, THEN THE Discovery_Client SHALL select the first record returned by the Agent Registry.
4. WHEN the Agent Registry returns no matching Registry_Records for the requested Tier, THE Discovery_Client SHALL fall back to the SSM_Parameter-based URL for that Tier.
5. IF the Agent Registry is unreachable or returns an error within the 5-second timeout, THEN THE Discovery_Client SHALL fall back to the SSM_Parameter-based URL for that Tier.
6. IF both the Agent Registry query and the SSM_Parameter-based URL retrieval fail, THEN THE Discovery_Client SHALL raise an initialization error indicating that no gateway endpoint could be resolved.

### Requirement 2: Fallback to SSM-Based Discovery

**User Story:** As a healthcare agent operator, I want the agent to fall back to SSM parameter-based endpoint URLs when the Agent Registry is unavailable, so that the agent remains operational during registry outages.

#### Acceptance Criteria

1. IF the Agent Registry does not respond within 5 seconds or returns an HTTP error status, THEN THE Discovery_Client SHALL retrieve the MCP gateway URL from the SSM_Parameter at the path defined in TIER_CONFIG for the current Tier.
2. IF both the Agent Registry and the SSM_Parameter retrieval fail, THEN THE Discovery_Client SHALL raise a RuntimeError with a message that includes the Tier name, the Agent Registry failure reason, and the SSM_Parameter failure reason.
3. WHEN the Discovery_Client falls back to SSM_Parameter retrieval, THE Discovery_Client SHALL log a warning message that includes the Tier name, the Agent Registry failure reason, and the SSM parameter path used as the fallback source.
4. THE Discovery_Client SHALL attempt the Agent Registry lookup before attempting the SSM_Parameter fallback.
5. IF the Agent Registry does not respond within 5 seconds or returns an HTTP error status, THEN THE Discovery_Client SHALL attempt SSM_Parameter retrieval no more than 1 time before raising a RuntimeError.

### Requirement 3: IAM-Based Authentication for Registry Access

**User Story:** As a security engineer, I want registry access to use IAM-based authentication, so that access control is consistent with the existing AWS credential model and no additional secrets are required.

#### Acceptance Criteria

1. THE Discovery_Client SHALL authenticate to the Agent Registry using the agent's existing IAM execution role credentials without requiring additional credential configuration or secret management.
2. THE Discovery_Client SHALL use the AWS SDK (boto3) Signature Version 4 signing for all Agent Registry API calls.
3. IF the IAM credentials lack permission to query the Agent Registry, THEN THE Discovery_Client SHALL log an error message that includes the IAM role ARN, the denied action name, and the registry resource ARN, and SHALL fall back to the SSM_Parameter-based URL.
4. IF the IAM credentials are expired or unavailable, THEN THE Discovery_Client SHALL log an error message indicating the credential failure type and SHALL fall back to the SSM_Parameter-based URL.

### Requirement 4: Registry Record Structure

**User Story:** As a platform engineer, I want registry records to contain tier, endpoint URL, and descriptive metadata, so that the agent can filter and select the correct gateway for each tenant tier.

#### Acceptance Criteria

1. THE Registry_Record SHALL contain a field identifying the associated Tier with a value of "basic" or "premium".
2. THE Registry_Record SHALL contain a field with the HTTPS URL of the MCP_Gateway endpoint, formatted as a complete URL of no more than 2048 characters starting with "https://".
3. THE Registry_Record SHALL contain a description field of no more than 256 characters identifying the gateway purpose (e.g., "Healthcare Lambda Gateway - Basic Tier").
4. THE Registry_Record SHALL contain a timestamp in ISO 8601 format (UTC) indicating when the record was last updated.
5. IF a Registry_Record is missing the Tier field, the endpoint URL field, or the timestamp field, THEN THE Discovery_Client SHALL skip that record and log a warning indicating the record identifier and which field is missing.

### Requirement 5: Deployment-Time Registry Creation and Publishing

**User Story:** As a DevOps engineer, I want the deployment script to create the Agent Registry and publish gateway records automatically, so that the registry is populated before the agent starts.

#### Acceptance Criteria

1. WHEN deploy.sh is executed, THE Deployment_Script SHALL invoke the Registry_Publisher after MCP gateways are created and before agents are configured.
2. WHEN the Agent Registry does not exist, THE Registry_Publisher SHALL create a new Agent Registry resource with the name "healthcare-mcp-registry" and wait up to 120 seconds for the registry to reach a ready state before proceeding.
3. WHEN the Agent Registry already exists, THE Registry_Publisher SHALL skip registry creation and proceed to publish records.
4. THE Registry_Publisher SHALL publish one Registry_Record for the basic Tier MCP_Gateway and one Registry_Record for the premium Tier MCP_Gateway, where each record contains the tier identifier and the gateway URL retrieved from the SSM parameter at "/app/healthcare/agentcore/{tier}_gateway_url".
5. WHEN a Registry_Record for a given Tier already exists, THE Registry_Publisher SHALL update the existing record with the current gateway URL rather than creating a duplicate.
6. THE Registry_Publisher SHALL store the Agent Registry ID as a String-type SSM_Parameter at the path "/app/healthcare/agentcore/registry_id".
7. IF registry creation fails or does not reach a ready state within 120 seconds, THEN THE Registry_Publisher SHALL exit with a non-zero status code and log an error message indicating the failure reason without proceeding to record publishing.
8. IF publishing a Registry_Record fails for a given Tier, THEN THE Registry_Publisher SHALL exit with a non-zero status code and log an error message indicating which Tier record failed, while preserving any records that were successfully published.

### Requirement 6: Integration with Existing Agent Initialization

**User Story:** As a developer, I want registry-based discovery to integrate seamlessly with the existing HealthcareAgent initialization flow, so that the change is transparent to the rest of the agent codebase.

#### Acceptance Criteria

1. THE HealthcareAgent SHALL use the Discovery_Client to resolve the MCP gateway URL instead of calling get_ssm_parameter directly for the gateway URL, where the Discovery_Client returns a fully-qualified HTTP or HTTPS URL string.
2. WHEN the Discovery_Client returns a gateway URL, THE HealthcareAgent SHALL pass the returned URL to initialize the MCPClient with the same bearer token and headers (X-Tier, X-Clinic-ID, X-S3-Prefix) as used with the current SSM-resolved URL.
3. THE Discovery_Client SHALL be importable as a standalone module from the agent package (e.g., `from agent.discovery_client import DiscoveryClient`) for independent testing without requiring HealthcareAgent instantiation.
4. THE Discovery_Client SHALL accept the Tier (one of the tiers defined in the agent's TIER_CONFIG) and AWS region as input parameters, where region defaults to the AWS_REGION environment variable or "us-east-1" if unset.
5. IF the Discovery_Client fails to resolve a gateway URL (due to registry unavailability, network error, or invalid tier), THEN THE HealthcareAgent SHALL raise a RuntimeError indicating the discovery failure reason within 30 seconds of the resolution attempt.

### Requirement 7: Registry Discovery Caching

**User Story:** As a platform engineer, I want discovered registry endpoints to be cached within the agent process lifetime, so that repeated initializations do not make redundant registry calls.

#### Acceptance Criteria

1. WHEN the Discovery_Client successfully resolves a gateway URL from the Agent Registry, THE Discovery_Client SHALL cache the result keyed by Tier and retain it for the lifetime of the agent process.
2. WHEN a cached URL exists for the requested Tier, THE Discovery_Client SHALL return the cached URL without querying the Agent Registry again.
3. IF the Discovery_Client resolves a gateway URL via the SSM_Parameter fallback, THEN THE Discovery_Client SHALL NOT cache the fallback result, so that a subsequent request for the same Tier will re-attempt the Agent Registry lookup.
4. THE Discovery_Client SHALL provide a method to clear all cached entries across all Tiers.
5. WHEN the cache has been cleared, THE Discovery_Client SHALL query the Agent Registry on the next resolution request as if no prior resolution had occurred.
