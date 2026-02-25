# Product Overview

Multi-tenant healthcare clinical document processing platform built on Amazon Bedrock AgentCore. Demonstrates complete tenant isolation across healthcare organizations with tier-based service levels.

## What It Does

AI-powered clinical document assistant that lets healthcare staff search, summarize, and analyze patient records and clinical documents. Each clinic is fully isolated — they can only see their own data.

## Service Tiers

- **Basic** — Primary care clinics (Clinics A–D). Document search, summarization via Nova Micro. Lower rate limits.
- **Premium** — Specialty care orgs (Hospitals A–B, Clinics E–F). All basic features plus web search for medical research, higher rate limits, Claude Sonnet model.

## Key Concepts

- **Tenant isolation**: Enforced via S3 prefixes, metadata filtering on Knowledge Bases, and hierarchical `actor_id` patterns for memory.
- **actor_id format**: `{tier}-{clinic_id}-{user_id}` (e.g., `premium-hospital-a-<uuid>`)
- **Memory namespace**: `clinic/{actorId}/facts/{sessionId}`, `clinic/{actorId}/preferences`
- **Authentication**: Amazon Cognito with JWT tokens carrying `custom:tenant_id` and `custom:clinic_id` claims.
- **Cost tracking**: Per-clinic attribution via OpenTelemetry baggage and Bedrock inference profile tags.
- **Tier routing**: Single `HealthcareAgent` class configured via `TIER_CONFIG` dict — no code duplication between tiers.
