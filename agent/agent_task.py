# Copyright 2026 Amazon.com and its affiliates; all rights reserved.
# SPDX-License-Identifier: MIT-0

"""Async task runner for agent invocations — shared across tiers."""

import os
import logging

from .context import TenantContext
from .memory_hook import MemoryHook
from .scoped_credentials import create_scoped_memory_client
from .utils import get_ssm_parameter
from .agent import HealthcareAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
            tier = TenantContext.get_tier() or "basic"
            memory_id = TenantContext.get_memory_id()
            if not memory_id:
                memory_id = get_ssm_parameter(f"/app/healthcare/memory/{tier}_id")

            # Get tenant context
            clinic_id = TenantContext.get_clinic_id() or "demo-clinic"
            user_id = TenantContext.get_user_id() or "demo-user"
            role = TenantContext.get_role() or "user"
            s3_prefix = TenantContext.get_s3_prefix() or f"{tier}-tier/{clinic_id}/"

            # Initialize MemoryHook with ABAC-scoped credentials
            # Each tenant gets a MemoryClient whose STS session tags
            # restrict access at the IAM level (not just application level)
            memory_hook = None
            try:
                scoped_client = create_scoped_memory_client(
                    tier=tier, clinic_id=clinic_id, user_id=user_id
                )
                memory_hook = MemoryHook(
                    memory_client=scoped_client,
                    memory_id=memory_id,
                    actor_id=actor_id,
                    session_id=session_id,
                )
                logger.info(
                    f"MemoryHook created with ABAC-scoped credentials: "
                    f"memory_id={memory_id}, actor_id={actor_id}"
                )
            except Exception as e:
                logger.error(f"Failed to create MemoryHook: {e}", exc_info=True)
                logger.error("Agent will run without conversation history")

            logger.info(
                f"Creating agent: tier={tier}, clinic={clinic_id}, user={user_id}"
            )

            agent = HealthcareAgent(
                bearer_token=gateway_access_token,
                memory_hook=memory_hook,
                tier=tier,
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
