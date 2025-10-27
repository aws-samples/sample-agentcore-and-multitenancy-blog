from agent_config_premium.context import CustomerSupportContext
from agent_config_premium.access_token import get_gateway_access_token
from agent_config_premium.agent_task import agent_task
from agent_config_premium.streaming_queue import StreamingQueue
from agent_config_premium.jwt_utils import extract_tenant_id_from_jwt
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from scripts.utils import get_ssm_parameter
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
async def invoke(payload, context):
    if not CustomerSupportContext.get_response_queue_ctx():
        CustomerSupportContext.set_response_queue_ctx(StreamingQueue())

    if not CustomerSupportContext.get_gateway_token_ctx():
        gateway_token = await get_gateway_access_token()
        CustomerSupportContext.set_gateway_token_ctx(gateway_token)
        
        # Hardcode tenant_id to premium for premium agent
        tenant_id = "premium"
        print(f"🔍 DEBUG: Premium agent hardcoded tenant_id: {tenant_id}")
        CustomerSupportContext.set_tenant_id_ctx(tenant_id)

    user_message = payload["prompt"]
    actor_id = payload["actor_id"]

    session_id = context.session_id

    if not session_id:
        raise Exception("Context session_id is not set")

    task = asyncio.create_task(
        agent_task(
            user_message=user_message,
            session_id=session_id,
            actor_id=actor_id,
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
