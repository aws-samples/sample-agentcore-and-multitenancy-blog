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
  - OpenTelemetry baggage for observability

Cost attribution is handled by Amazon Bedrock Projects via the Mantle
(OpenAI-compatible) endpoint. Each tier has a dedicated project whose
tags flow into AWS Cost Explorer. See agent/agent.py for the model
provider configuration.

Authentication flow (end-to-end JWT):
  1. AgentCore Runtime's Inbound JWT Authorizer validates the token signature,
     issuer, audience, and expiry before the agent code runs.
  2. The Lambda proxy decodes the JWT (without verification) to extract tenant
     claims and enriches the payload with tier/clinic_id/user_id.
  3. This entrypoint reads tenant context from the payload.
  4. The incoming JWT is read from request_headers["Authorization"] (via
     requestHeaderAllowlist) and stored in TenantContext.gateway_token.
  5. Outbound gateway calls forward the same user JWT as a Bearer token.
     The gateway validates it via its own CUSTOM_JWT authorizer (same
     Cognito pool). No second app client or managed credential needed.
"""

import os
import logging
import asyncio
import uuid
import time
import traceback

if "AWS_REGION" not in os.environ:
    os.environ["AWS_REGION"] = "us-east-1"

logging.basicConfig(level=logging.INFO, force=True)
logger = logging.getLogger(__name__)
logger.info("main.py: starting imports...")

_t0 = time.time()

try:
    from bedrock_agentcore.runtime import BedrockAgentCoreApp
    logger.info(f"main.py: imported BedrockAgentCoreApp ({time.time()-_t0:.2f}s)")
except Exception as e:
    logger.error(f"main.py: IMPORT FAILED: {e}\n{traceback.format_exc()}")
    raise

# Heavy imports deferred to first invocation to stay within 30s runtime init deadline.
# AgentCore requires app = BedrockAgentCoreApp() + app.run() to complete within 30s.
# strands, mcp, opentelemetry, boto3, etc. are imported lazily inside invoke().
_lazy_imports_done = False
TenantContext = None
agent_task = None
StreamingQueue = None
MemorySessionManager = None
get_ssm_parameter = None
baggage = None
otel_context = None


def _do_lazy_imports():
    global _lazy_imports_done, TenantContext, agent_task, StreamingQueue
    global MemorySessionManager, get_ssm_parameter, baggage, otel_context
    if _lazy_imports_done:
        return
    _t1 = time.time()
    from agent.context import TenantContext as _TC
    from agent.agent_task import agent_task as _at
    from agent.streaming_queue import StreamingQueue as _SQ
    from bedrock_agentcore.memory import MemorySessionManager as _MSM
    from scripts.utils import get_ssm_parameter as _gsp
    from opentelemetry import baggage as _bag, context as _ctx
    TenantContext = _TC
    agent_task = _at
    StreamingQueue = _SQ
    MemorySessionManager = _MSM
    get_ssm_parameter = _gsp
    baggage = _bag
    otel_context = _ctx
    _lazy_imports_done = True
    logger.info(f"main.py: lazy imports done ({time.time()-_t1:.2f}s)")

os.environ["STRANDS_OTEL_ENABLE_CONSOLE_EXPORT"] = "true"
os.environ["STRANDS_TOOL_CONSOLE_MODE"] = "enabled"
os.environ["DEFAULT_TIMEZONE"] = "America/New_York"

# Default tier (overridden per-request from payload)
AGENT_TIER = os.environ.get("AGENT_TIER", "basic")

# KB IDs loaded lazily on first request to avoid blocking runtime initialization
KB_IDS = {}
_kb_ids_loaded = False


def _ensure_kb_ids():
    global _kb_ids_loaded
    if _kb_ids_loaded:
        return
    _kb_ids_loaded = True
    for _tier in ("basic", "premium"):
        try:
            KB_IDS[_tier] = get_ssm_parameter(f"/app/healthcare/knowledge_base/{_tier}_kb_id")
        except Exception:
            KB_IDS[_tier] = ""
    os.environ["KNOWLEDGE_BASE_ID"] = KB_IDS.get(AGENT_TIER, KB_IDS.get("basic", ""))
    logger.info(f"Loaded KB IDs — basic: {KB_IDS.get('basic')}, premium: {KB_IDS.get('premium')}")


logging.basicConfig(level=logging.INFO, force=True)
logger = logging.getLogger(__name__)

logger.info(f"main.py: creating BedrockAgentCoreApp... ({time.time()-_t0:.2f}s)")
app = BedrockAgentCoreApp()
logger.info(f"main.py: app created ({time.time()-_t0:.2f}s)")




@app.entrypoint
async def invoke(payload, context=None):
    # Lazy-import heavy dependencies on first request (not at module level)
    # This keeps runtime initialization under the 30s deadline.
    _do_lazy_imports()

    # Lazy-load KB IDs on first request (avoids blocking runtime init)
    _ensure_kb_ids()

    # Initialize streaming queue
    if not TenantContext.get_response_queue():
        TenantContext.set_response_queue(StreamingQueue())

    # Extract tenant context from payload (enriched by Lambda proxy)
    if not TenantContext.get_tier():
        # Tenant context comes from the payload (enriched by Lambda proxy)
        tier = payload.get("tier", AGENT_TIER)
        clinic_id = payload.get("clinic_id", "demo-clinic")
        user_id = payload.get("user_id", "demo-user")
        role = payload.get("role", "user")

        # Extract the incoming JWT from request headers (forwarded via
        # requestHeaderAllowlist: ["Authorization"] on the Runtime config).
        # This token is already validated by the Runtime's Inbound JWT Authorizer.
        # We store it so the agent can forward it to the Gateway (CUSTOM_JWT).
        if context and hasattr(context, "request_headers") and context.request_headers:
            auth_header = context.request_headers.get("Authorization", "")
            if auth_header:
                token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else auth_header
                TenantContext.set_gateway_token(token)
                logger.info("JWT extracted from request headers for gateway auth")
            else:
                logger.warning("Authorization header not found in request_headers")
        else:
            logger.warning(f"No request_headers on context (context={context is not None})")

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

        # OpenTelemetry baggage for per-tenant observability
        # (Cost attribution is handled by Bedrock Projects via the Mantle endpoint;
        #  baggage is retained for tracing and log correlation.)
        ctx = baggage.set_baggage("tier", tier)
        ctx = baggage.set_baggage("clinic_id", clinic_id, context=ctx)
        ctx = baggage.set_baggage("actor_id", actor_id, context=ctx)
        otel_context.attach(ctx)

    # Initialize Memory Session
    memory_id = TenantContext.get_memory_id()
    actor_id = TenantContext.get_actor_id()

    session_id = (
        context.session_id
        if context and hasattr(context, "session_id")
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
