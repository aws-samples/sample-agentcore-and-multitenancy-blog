# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Initial release of Multi-Tenant Healthcare Agent with Amazon Bedrock AgentCore
- Multi-tenant data isolation via Knowledge Base metadata filtering
- Memory isolation with hierarchical actor_id
- Tier-based routing (Basic and Premium)
- Cognito JWT authentication and tenant identity
- Cost attribution via OpenTelemetry and inference profiles
- Gateway header propagation for tenant context
- Streamlit web UI for chat interaction
