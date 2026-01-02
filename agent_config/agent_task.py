from .context import CustomerSupportContext
from .memory_hook_provider import MemoryHook
from .utils import get_ssm_parameter
from agent_config.agent import CustomerSupport  # Your custom agent class
from agent_config.tools.google import get_calendar_events_today, create_calendar_event
from bedrock_agentcore.memory import MemoryClient
import logging

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

memory_client = MemoryClient()


async def agent_task(user_message: str, session_id: str, actor_id: str, memory_session=None):
    agent = CustomerSupportContext.get_agent_ctx()

    response_queue = CustomerSupportContext.get_response_queue_ctx()
    gateway_access_token = CustomerSupportContext.get_gateway_token_ctx()

    if not gateway_access_token:
        raise RuntimeError("Gateway Access token is none")
    try:
        if agent is None:
            # Use provided memory_session or create new MemoryHook
            if memory_session:
                logger.info(f"✅ Using provided memory session for actor_id={actor_id}")
                memory_hook = MemoryHook(
                    memory_client=memory_client,
                    memory_id=CustomerSupportContext.get_memory_id_ctx() or get_ssm_parameter("/app/healthcare/memory/basic_id"),
                    actor_id=actor_id,
                    session_id=session_id,
                )
            else:
                logger.warning(f"⚠️  No memory session provided, creating fallback MemoryHook")
                memory_hook = MemoryHook(
                    memory_client=memory_client,
                    memory_id=get_ssm_parameter("/app/customersupport/agentcore/memory_id"),
                    actor_id=actor_id,
                    session_id=session_id,
                )

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
                tools=[get_calendar_events_today, create_calendar_event],
                guardrail_id=get_ssm_parameter("/app/customersupport/agentcore/basic_guardrail_id"),
            )

            CustomerSupportContext.set_agent_ctx(agent)

        async for chunk in agent.stream(user_query=user_message):
            await response_queue.put(chunk)

    except Exception as e:
        logger.exception("Agent execution failed.")
        await response_queue.put(f"Error: {str(e)}")
    finally:
        await response_queue.finish()
