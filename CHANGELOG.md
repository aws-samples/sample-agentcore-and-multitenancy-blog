# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- AgentCore Runtimes are now declared in `prerequisite/agentcore_runtime.yaml`
  using `AWS::BedrockAgentCore::Runtime`, replacing the `agentcore configure`
  and `agentcore deploy` calls in `deploy.sh`.
- Runtimes run on AgentCore Runtime platform version V2, which restores a
  prepared snapshot per session instead of initializing the environment. Set
  `AGENTCORE_PLATFORM_VERSION=V1` to deploy on the original platform.
- The Streamlit app reads agent ARNs from SSM rather than from
  `.bedrock_agentcore.yaml`.
- `scripts/cleanup.sh` deletes the runtime stack instead of deleting runtimes
  directly, and still removes unmanaged runtimes left by older deploys.

### Removed

- `bedrock-agentcore-starter-toolkit` dependency. It is no longer supported
  upstream and cannot set the runtime platform version.

### Added

- Initial release of Multi-Tenant Healthcare Agent with Amazon Bedrock AgentCore
- Multi-tenant data isolation via Knowledge Base metadata filtering
- Memory isolation with hierarchical actor_id
- Tier-based routing (Basic and Premium)
- Cognito JWT authentication and tenant identity
- Cost attribution via OpenTelemetry and inference profiles
- Gateway header propagation for tenant context
- Streamlit web UI for chat interaction
- `scripts/package_agent.sh` builds the direct-code-deploy bundle with
  linux/aarch64 wheels and uploads it to S3 under a content-hashed key, so a
  code change produces a new key and CloudFormation rolls the runtime forward.
