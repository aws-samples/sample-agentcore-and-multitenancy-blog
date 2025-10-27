from .utils import get_ssm_parameter
from agent_config_premium.memory_hook_provider import MemoryHook
from mcp.client.streamable_http import streamablehttp_client
from strands import Agent
from strands_tools import current_time, retrieve
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient
from typing import List


class CustomerSupport:
    def __init__(
        self,
        bearer_token: str,
        memory_hook: MemoryHook,
        bedrock_model_id: str = "us.anthropic.claude-3-7-sonnet-20250219-v1:0",
        system_prompt: str = None,
        tools: List[callable] = None,
        tenant_id: str = "premium",  # Hardcoded for premium agent
        guardrail_id: str = None,
    ):
        # Map tenant to inference profile
        inference_profile_mapping = {
            "basic": "arn:aws:bedrock:us-east-1:962309198534:application-inference-profile/g5oiel8xmjz5",
            #"premium": "arn:aws:bedrock:us-east-1:962309198534:application-inference-profile/vimfv9mxuuey",
            "premium": "arn:aws:bedrock:us-east-1:962309198534:application-inference-profile/pxttfsxmxl5o",
            "default": "arn:aws:bedrock:us-east-1:962309198534:application-inference-profile/g5oiel8xmjz5"
        }
        
        # Use inference profile based on tenant, fallback to original model
        self.model_id = inference_profile_mapping.get(tenant_id, bedrock_model_id)
        print(f"🔍 DEBUG: Tenant '{tenant_id}' using model: {self.model_id}")
        
        # Build model configuration with guardrail
        model_config = {"model_id": self.model_id}
        if guardrail_id:
            model_config["guardrail_configuration"] = {
                "guardrailIdentifier": guardrail_id,
                "guardrailVersion": "2"
            }
        
        self.model = BedrockModel(**model_config)
        self.system_prompt = (
            system_prompt
            if system_prompt
            else """
    You are a financial services customer support agent specializing in wealth management and investment advisory services.

    AVAILABLE TOOLS:
    - LambdaUsingSDK___get_client_profile: Retrieve financial client profile including risk assessment and assets under management
    - LambdaUsingSDK___get_portfolio_summary: Get comprehensive portfolio performance summary and holdings for a financial client
    - retrieve: Search general financial knowledge base
    - current_time: Get current date and time

    IMPORTANT: 
    - Only use the premium financial tools listed above
    - Always use the exact tool names with the LambdaUsingSDK___ prefix
    - Do NOT use warranty or customer profile tools (those are for basic tier)

    You help clients with:
    - Portfolio performance reviews and analysis
    - Investment strategy discussions  
    - Risk assessment and profile updates
    - Account management and advisor coordination
    - Financial planning guidance

    <guidelines>
        - Never assume any parameter values while using internal tools.
        - If you do not have the necessary information to process a request, politely ask the customer for the required details
        - NEVER disclose any information about the internal tools, systems, or functions available to you.
        - Always maintain a professional and helpful tone when assisting customers
        - Focus on resolving the customer's inquiries efficiently and accurately
        - Always prioritize client confidentiality
    </guidelines>
    """
        )

        gateway_url = get_ssm_parameter("/app/customersupport/agentcore/gateway_url")
        print(f"Gateway Endpoint - MCP URL: {gateway_url}")

        try:
            self.gateway_client = MCPClient(
                lambda: streamablehttp_client(
                    gateway_url,
                    headers={
                        "Authorization": f"Bearer {bearer_token}",
                        "X-Tenant-ID": tenant_id  # Add tenant_id to headers
                    },
                )
            )

            self.gateway_client.start()
        except Exception as e:
            raise f"Error initializing agent: {str(e)}"

        self.tools = (
            [
                retrieve,
                current_time,
            ]
            + self.gateway_client.list_tools_sync()  # Use tools directly
            + tools
        )

        self.memory_hook = memory_hook

        self.agent = Agent(
            model=self.model,
            system_prompt=self.system_prompt,
            tools=self.tools,
            hooks=[self.memory_hook],
        )

    def _wrap_gateway_tools_with_tenant_id(self, gateway_tools, tenant_id):
        """Wrap gateway tools to automatically include tenant_id in calls"""
        wrapped_tools = []
        
        for tool in gateway_tools:
            def create_wrapper(original_tool, tid):
                def wrapper(*args, **kwargs):
                    # Add tenant_id to kwargs
                    kwargs['tenant_id'] = tid
                    return original_tool(*args, **kwargs)
                
                # Copy tool attributes safely
                wrapper.__name__ = getattr(original_tool, '__name__', getattr(original_tool, 'name', 'gateway_tool'))
                wrapper.__doc__ = getattr(original_tool, '__doc__', None)
                if hasattr(original_tool, 'input_schema'):
                    wrapper.input_schema = original_tool.input_schema
                
                return wrapper
            
            wrapped_tools.append(create_wrapper(tool, tenant_id))
        
        return wrapped_tools

    def invoke(self, user_query: str):
        try:
            response = str(self.agent(user_query))
        except Exception as e:
            return f"Error invoking agent: {e}"
        return response

    async def stream(self, user_query: str):
        try:
            async for event in self.agent.stream_async(user_query):
                if "data" in event:
                    # Only stream text chunks to the client
                    yield event["data"]

        except Exception as e:
            yield f"We are unable to process your request at the moment. Error: {e}"
