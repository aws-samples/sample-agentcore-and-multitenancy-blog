# Copyright 2026 Amazon.com and its affiliates; all rights reserved.
# SPDX-License-Identifier: MIT-0

"""
Single AgentCore entrypoint for all tiers.

Tier is determined from the incoming payload (tier field), not from
separate codepaths. This means one deployed agent binary can serve both
basic and premium tenants — or you can deploy two instances of the same
code with different KB IDs via environment variables.

Multi-tenancy concerns handled here:
  - Tenant identity extraction from payload AND propagated JWT header
  - Hierarchical actor_id construction for memory isolation
  - Per-tenant memory resource routing
  - OpenTelemetry baggage for cost attribution

Authentication flow (hybrid):
  1. AgentCore Runtime's Inbound JWT Authorizer validates the token signature,
     issuer, audience, and expiry before the agent code runs.
  2. The Lambda proxy decodes the JWT (without verification) to extract tenant
     claims and enriches the payload with tier/clinic_id/user_id.
  3. This entrypoint reads tenant context from the payload. It can also read
     the propagated Authorization header (via requestHeaderAllowlist) as a
     secondary source for claim extraction.
"""

import os
import logging
import asyncio
import uuid

if "AWS_REGION" not in os.environ:
    os.environ["AWS_REGION"] = "us-east-1"

import jwt as pyjwt  # For decoding propagated JWT header
from agent.context import TenantContext
from agent.access_token import get_gateway_access_token
from agent.agent_task import agent_task
from agent.streaming_queue import StreamingQueue
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from bedrock_agentcore.memory import MemorySessionManager
from scripts.utils import get_ssm_parameter
from opentelemetry import baggage, context

os.environ["STRANDS_OTEL_ENABLE_CONSOLE_EXPORT"] = "true"
os.environ["STRANDS_TOOL_CONSOLE_MODE"] = "enabled"
os.environ["DEFAULT_TIMEZONE"] = "America/New_York"

# Default tier (overridden per-request from payload)
AGENT_TIER = os.environ.get("AGENT_TIER", "basic")

# Load both KB IDs at startup so the correct one can be selected per-request
KB_IDS = {}
for _tier in ("basic", "premium"):
    try:
        KB_IDS[_tier] = get_ssm_parameter(f"/app/healthcare/knowledge_base/{_tier}_kb_id")
    except Exception:
        KB_IDS[_tier] = ""

# Default to basic until a request arrives with tenant context
os.environ["KNOWLEDGE_BASE_ID"] = KB_IDS.get(AGENT_TIER, KB_IDS.get("basic", ""))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logger.info(f"Loaded KB IDs — basic: {KB_IDS.get('basic')}, premium: {KB_IDS.get('premium')}")

app = BedrockAgentCoreApp()


def _extract_claims_from_header(agentcore_context) -> dict:
    """
    Extract tenant claims from the propagated Authorization header.

    The JWT signature has already been validated by AgentCore Runtime's
    Inbound JWT Authorizer, so we skip signature verification here.
    This is the pattern recommended by the AgentCore docs (Step 6).
    """
    claims = {}
    if not agentcore_context or not hasattr(agentcore_context, 'request_headers'):
        return claims

    auth_header = agentcore_context.request_headers.get('Authorization', '')
    if not auth_header:
        return claims

    token = auth_header.replace('Bearer ', '') if auth_header.startswith('Bearer ') else auth_header
    try:
        # Skip signature validation — AgentCore Runtime already validated the token
        decoded = pyjwt.decode(token, options={"verify_signature": False})
        if 'custom:tier' in decoded:
            claims['tier'] = decoded['custom:tier']
        if 'custom:clinic_id' in decoded:
            claims['clinic_id'] = decoded['custom:clinic_id']
        if 'custom:role' in decoded:
            claims['role'] = decoded['custom:role']
        if 'cognito:username' in decoded:
            claims['user_id'] = decoded['cognito:username']
        elif 'sub' in decoded:
            claims['user_id'] = decoded['sub']
        logger.info(f"Extracted claims from propagated JWT header: {claims}")
    except Exception as e:
        logger.warning(f"Could not decode propagated JWT header: {e}")

    return claims


@app.entrypoint
async def invoke(payload, agentcore_context=None):
    # Initialize streaming queue
    if not TenantContext.get_response_queue():
        TenantContext.set_response_queue(StreamingQueue())

    # Initialize gateway token and extract tenant info
    if not TenantContext.get_gateway_token():
        gateway_token = await get_gateway_access_token()
        TenantContext.set_gateway_token(gateway_token)

        # Primary source: tenant context from payload (enriched by Lambda proxy)
        # Fallback: claims from propagated Authorization header
        jwt_claims = _extract_claims_from_header(agentcore_context)

        tier = payload.get("tier") or jwt_claims.get("tier", AGENT_TIER)
        clinic_id = payload.get("clinic_id") or jwt_claims.get("clinic_id", "demo-clinic")
        user_id = payload.get("user_id") or jwt_claims.get("user_id", "demo-user")
        role = payload.get("role") or jwt_claims.get("role", "user")

        # Select the correct Knowledge Base for this tenant's tier
        kb_id = KB_IDS.get(tier, KB_IDS.get("basic", ""))
        os.environ["KNOWLEDGE_BASE_ID"] = kb_id
        logger.info(f"Selected KB for tier '{tier}': {kb_id}")

        # Construct hierarchical identifiers for isolation
        actor_id = f"{tier}-{clinic_id}-{user_id}"
        s3_prefix = f"{tier}-tier/{clinic_id}/"
        memory_id = get_ssm_parameter(f"/app/healthcare/memory/{tier}_id")

        logger.info(
            f"Tenant context: tier={tier}, clinic={clinic_id}, "
            f"actor_id={actor_id}, memory_id={memory_id}"
        )

        # Set all tenant context
        TenantContext.set_tier(tier)
        TenantContext.set_clinic_id(clinic_id)
        TenantContext.set_user_id(user_id)
        TenantContext.set_actor_id(actor_id)
        TenantContext.set_s3_prefix(s3_prefix)
        TenantContext.set_memory_id(memory_id)
        TenantContext.set_role(role)

        # OpenTelemetry baggage for per-tenant cost tracking
        ctx = baggage.set_baggage("tier", f"{tier}-{clinic_id}")
        ctx = baggage.set_baggage("tier", tier, context=ctx)
        ctx = baggage.set_baggage("clinic_id", clinic_id, context=ctx)
        ctx = baggage.set_baggage("actor_id", actor_id, context=ctx)
        context.attach(ctx)

    # Initialize Memory Session
    memory_id = TenantContext.get_memory_id()
    actor_id = TenantContext.get_actor_id()

    session_id = (
        agentcore_context.session_id
        if agentcore_context and hasattr(agentcore_context, "session_id")
        else str(uuid.uuid4())
    )

    memory_session = None
    try:
        memory_manager = MemorySessionManager(
            memory_id=memory_id,
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
        )
        memory_session = memory_manager.create_memory_session(
            actor_id=actor_id, session_id=session_id
        )
        logger.info(f"Memory session created: session_id={session_id}, actor_id={actor_id}")
    except Exception as e:
        logger.error(f"Failed to initialize memory session: {e}")

    # Run agent task
    user_message = payload["prompt"]
    task = asyncio.create_task(
        agent_task(
            user_message=user_message,
            session_id=session_id,
            actor_id=actor_id,
            memory_session=memory_session,
        )
    )

    response_queue = TenantContext.get_response_queue()

    async def stream_output():
        async for item in response_queue.stream():
            yield item
        await task

    return stream_output()


if __name__ == "__main__":
    app.run()
