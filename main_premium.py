from agent_config_premium.context import CustomerSupportContext
from agent_config_premium.access_token import get_gateway_access_token
from agent_config_premium.agent_task import agent_task
from agent_config_premium.streaming_queue import StreamingQueue
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from bedrock_agentcore.memory import MemorySessionManager
from scripts.utils import get_ssm_parameter
from opentelemetry import baggage, context
import asyncio
import logging
import os

# Environment flags
os.environ["STRANDS_OTEL_ENABLE_CONSOLE_EXPORT"] = "true"
os.environ["STRANDS_TOOL_CONSOLE_MODE"] = "enabled"

# Use premium knowledge base
os.environ["KNOWLEDGE_BASE_ID"] = get_ssm_parameter(
    "/app/customersupport/premium_knowledge_base/knowledge_base_id"
)

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Bedrock app and global agent instance
app = BedrockAgentCoreApp()


@app.entrypoint
async def invoke(payload, agentcore_context):
    # Initialize response queue if not set
    if not CustomerSupportContext.get_response_queue_ctx():
        CustomerSupportContext.set_response_queue_ctx(StreamingQueue())

    # Initialize gateway token and extract tenant info from payload
    if not CustomerSupportContext.get_gateway_token_ctx():
        gateway_token = await get_gateway_access_token()
        CustomerSupportContext.set_gateway_token_ctx(gateway_token)
        
        # Extract tenant information from payload (forwarded by API Gateway Lambda)
        # Premium agent always uses premium tier
        tier = 'premium'
        clinic_id = payload.get('clinic_id', 'demo-hospital')
        user_id = payload.get('user_id', 'demo-user')
        
        # Construct hierarchical identifiers
        actor_id = f"{tier}-{clinic_id}-{user_id}"
        tenant_key = f"{tier}-{clinic_id}"
        memory_id = 'healthcare-premium-memory'
        s3_prefix = f"{tier}-tier/{clinic_id}/"
        role = payload.get('role', 'user')
        
        tenant_info = {
            'tier': tier,
            'clinic_id': clinic_id,
            'user_id': user_id,
            'actor_id': actor_id,
            'tenant_key': tenant_key,
            'memory_id': memory_id,
            's3_prefix': s3_prefix,
            'role': role
        }
        logger.info(f"✅ Extracted tenant info from payload: {tenant_info}")
        
        # Set all tenant context variables
        CustomerSupportContext.set_tenant_id_ctx(tenant_info['tier'])
        CustomerSupportContext.set_clinic_id_ctx(tenant_info['clinic_id'])
        CustomerSupportContext.set_user_id_ctx(tenant_info['user_id'])
        CustomerSupportContext.set_actor_id_ctx(tenant_info['actor_id'])
        CustomerSupportContext.set_tenant_key_ctx(tenant_info['tenant_key'])
        CustomerSupportContext.set_s3_prefix_ctx(tenant_info['s3_prefix'])
        CustomerSupportContext.set_memory_id_ctx(tenant_info['memory_id'])
        CustomerSupportContext.set_role_ctx(tenant_info.get('role', 'user'))
        
        # Set OpenTelemetry baggage for observability and cost tracking
        ctx = baggage.set_baggage("tenant_id", tenant_info['tenant_key'])
        ctx = baggage.set_baggage("tier", tenant_info['tier'], context=ctx)
        ctx = baggage.set_baggage("clinic_id", tenant_info['clinic_id'], context=ctx)
        ctx = baggage.set_baggage("actor_id", tenant_info['actor_id'], context=ctx)
        context.attach(ctx)
        logger.info(f"📊 OpenTelemetry baggage set for cost tracking: tier={tenant_info['tier']}, clinic={tenant_info['clinic_id']}, actor={tenant_info['actor_id']}")

    # Initialize Memory Session Manager with tier-specific memory (premium)
    memory_id = CustomerSupportContext.get_memory_id_ctx()
    actor_id = CustomerSupportContext.get_actor_id_ctx()
    
    logger.info(f"💾 Initializing Memory Session Manager: memory_id={memory_id}, actor_id={actor_id}")
    
    try:
        memory_manager = MemorySessionManager(
            memory_id=memory_id,
            region_name=os.environ.get('AWS_REGION', 'us-east-1')
        )
        
        # Create memory session with user-specific actor_id for complete isolation
        session_id = agentcore_context.session_id
        if not session_id:
            raise Exception("Context session_id is not set")
        
        memory_session = memory_manager.create_memory_session(
            actor_id=actor_id,
            session_id=session_id
        )
        logger.info(f"✅ Memory session created: session_id={session_id}, actor_id={actor_id}")
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize memory session: {e}")
        # Continue without memory if initialization fails
        memory_session = None

    # Extract user message
    user_message = payload["prompt"]

    # Create agent task with memory session
    task = asyncio.create_task(
        agent_task(
            user_message=user_message,
            session_id=session_id,
            actor_id=actor_id,
            memory_session=memory_session  # Pass memory session to agent task
        )
    )

    response_queue = CustomerSupportContext.get_response_queue_ctx()

    async def stream_output():
        async for item in response_queue.stream():
            yield item
        await task  # Ensure task completion

    return stream_output()


if __name__ == "__main__":
    app.run()
