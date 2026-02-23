import os
import logging

from .context import CustomerSupportContext
from .memory_hook_provider import MemoryHook
from .utils import get_ssm_parameter
from agent_config.agent import CustomerSupport  # Your custom agent class
# from agent_config.tools.google import get_calendar_events_today, create_calendar_event  # Commented out — requires Google credentials provider SSM parameter
from bedrock_agentcore.memory import MemoryClient

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Defer MemoryClient creation to ensure AWS_REGION is set by main.py first
_memory_client = None


def _get_memory_client():
    global _memory_client
    if _memory_client is None:
        region = os.environ.get("AWS_REGION", "us-east-1")
        logger.info(f"💾 Creating MemoryClient with region={region}")
        _memory_client = MemoryClient(region_name=region)
    return _memory_client


async def agent_task(user_message: str, session_id: str, actor_id: str, memory_session=None):
    agent = CustomerSupportContext.get_agent_ctx()

    response_queue = CustomerSupportContext.get_response_queue_ctx()
    gateway_access_token = CustomerSupportContext.get_gateway_token_ctx()

    if not gateway_access_token:
        raise RuntimeError("Gateway Access token is none")
    try:
        if agent is None:
            # Initialize MemoryHook for basic tier conversation history
            try:
                if memory_session:
                    logger.info(f"✅ Using provided memory session for actor_id={actor_id}")
                    resolved_memory_id = CustomerSupportContext.get_memory_id_ctx() or get_ssm_parameter("/app/healthcare/memory/basic_id")
                else:
                    logger.warning(f"⚠️  No memory session provided, creating fallback MemoryHook")
                    resolved_memory_id = get_ssm_parameter("/app/healthcare/memory/basic_id")
                
                logger.info(f"💾 Basic MemoryHook init: memory_id={resolved_memory_id}, actor_id={actor_id}, session_id={session_id}")
                
                memory_hook = MemoryHook(
                    memory_client=_get_memory_client(),
                    memory_id=resolved_memory_id,
                    actor_id=actor_id,
                    session_id=session_id,
                )
                logger.info(f"✅ Basic MemoryHook created successfully")
            except Exception as e:
                logger.error(f"❌ Failed to create basic MemoryHook: {e}", exc_info=True)
                logger.error(f"   Falling back to no memory — agent will run without conversation history")
                memory_hook = None

            # Get tenant context for healthcare multi-tenancy
            tenant_id = CustomerSupportContext.get_tenant_id_ctx() or "basic"
            clinic_id = CustomerSupportContext.get_clinic_id_ctx() or "demo-clinic"
            user_id = CustomerSupportContext.get_user_id_ctx() or "demo-user"
            role = CustomerSupportContext.get_role_ctx() or "user"
            s3_prefix = CustomerSupportContext.get_s3_prefix_ctx() or "basic-tier/demo-clinic/"
            
            logger.info(f"🏥 Creating agent for tenant: tier={tenant_id}, clinic={clinic_id}, user={user_id}, role={role}")

            agent = CustomerSupport(
                bearer_token=gateway_access_token,
                memory_hook=memory_hook,
                tenant_id=tenant_id,
                clinic_id=clinic_id,
                user_id=user_id,
                role=role,
                s3_prefix=s3_prefix,
                tools=[],  # Google tools commented out — requires credentials provider setup
                # tools=[get_calendar_events_today, create_calendar_event],
                # guardrail_id=get_ssm_parameter("/app/healthcare/agentcore/basic_guardrail_id"),  # Removed for now
            )

            CustomerSupportContext.set_agent_ctx(agent)

        async for chunk in agent.stream(user_query=user_message):
            await response_queue.put(chunk)

    except Exception as e:
        logger.exception("Agent execution failed.")
        await response_queue.put(f"Error: {str(e)}")
    finally:
        await response_queue.finish()
