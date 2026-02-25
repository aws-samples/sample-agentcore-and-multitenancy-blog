"""Async task runner for agent invocations — shared across tiers."""

import os
import logging

from .context import TenantContext
from .memory_hook import MemoryHook
from .utils import get_ssm_parameter
from .agent import HealthcareAgent
from bedrock_agentcore.memory import MemoryClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_memory_client = None


def _get_memory_client():
    global _memory_client
    if _memory_client is None:
        region = os.environ.get("AWS_REGION", "us-east-1")
        _memory_client = MemoryClient(region_name=region)
    return _memory_client


async def agent_task(
    user_message: str, session_id: str, actor_id: str, memory_session=None
):
    agent = TenantContext.get_agent()
    response_queue = TenantContext.get_response_queue()
    gateway_access_token = TenantContext.get_gateway_token()

    if not gateway_access_token:
        raise RuntimeError("Gateway access token is not set")

    try:
        if agent is None:
            # Resolve tier-specific memory ID
            tenant_id = TenantContext.get_tenant_id() or "basic"
            memory_id = TenantContext.get_memory_id()
            if not memory_id:
                memory_id = get_ssm_parameter(f"/app/healthcare/memory/{tenant_id}_id")

            # Initialize MemoryHook for tenant-isolated conversation history
            memory_hook = None
            try:
                memory_hook = MemoryHook(
                    memory_client=_get_memory_client(),
                    memory_id=memory_id,
                    actor_id=actor_id,
                    session_id=session_id,
                )
                logger.info(
                    f"MemoryHook created: memory_id={memory_id}, actor_id={actor_id}"
                )
            except Exception as e:
                logger.error(f"Failed to create MemoryHook: {e}", exc_info=True)
                logger.error("Agent will run without conversation history")

            # Get tenant context
            clinic_id = TenantContext.get_clinic_id() or "demo-clinic"
            user_id = TenantContext.get_user_id() or "demo-user"
            role = TenantContext.get_role() or "user"
            s3_prefix = TenantContext.get_s3_prefix() or f"{tenant_id}-tier/{clinic_id}/"

            logger.info(
                f"Creating agent: tier={tenant_id}, clinic={clinic_id}, user={user_id}"
            )

            agent = HealthcareAgent(
                bearer_token=gateway_access_token,
                memory_hook=memory_hook,
                tenant_id=tenant_id,
                clinic_id=clinic_id,
                user_id=user_id,
                role=role,
                s3_prefix=s3_prefix,
                tools=[],
            )

            TenantContext.set_agent(agent)

        async for chunk in agent.stream(user_query=user_message):
            await response_queue.put(chunk)

    except Exception as e:
        logger.exception("Agent execution failed.")
        await response_queue.put(f"Error: {str(e)}")
    finally:
        await response_queue.finish()
