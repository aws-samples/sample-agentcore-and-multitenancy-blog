from .utils import get_ssm_parameter
from agent_config.memory_hook_provider import MemoryHook
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
        tenant_id: str = "basic",
        clinic_id: str = "demo-clinic",
        user_id: str = "demo-user",
        role: str = "user",
        s3_prefix: str = "basic-tier/demo-clinic/",
        guardrail_id: str = None,
    ):
        # Map tenant to inference profile (placeholders - will be updated by configure_deployment.py)
        inference_profile_mapping = {
            "basic": "arn:aws:bedrock:us-east-1:ACCOUNT_ID:application-inference-profile/BASIC_PROFILE_ID",
            "premium": "arn:aws:bedrock:us-east-1:ACCOUNT_ID:application-inference-profile/PREMIUM_PROFILE_ID",
            "default": "arn:aws:bedrock:us-east-1:ACCOUNT_ID:application-inference-profile/BASIC_PROFILE_ID"
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
            else f"""
You are a helpful clinical document assistant for a healthcare clinic.

YOUR ASSIGNED CONTEXT:
- Clinic: {clinic_id}
- Tier: {tenant_id}
- User: {user_id} (Role: {role})
- Document Scope: {s3_prefix}

AVAILABLE TOOLS:
- patient_context: Retrieve patient metadata (demographics, conditions, allergies, medications, visit history)
  * Use patient_id for single patient lookup
  * Use list_patients=true to get all patients for the clinic
  * Automatically filtered to your clinic for security
- clinic_config: Get clinic configuration (specialty, services, hours, providers)
  * Defaults to your clinic if no clinic_id specified
- retrieve: Search knowledge base for medical information and clinical documents
  * Searches documents under your clinic's scope: {s3_prefix}
- current_time: Get current date and time

CRITICAL SECURITY RULES:
1. You can ONLY access data for clinic: {clinic_id}
2. All tools automatically filter to your clinic - you cannot access other clinics' data
3. Patient data is protected - only accessible within your clinic scope
4. Document searches are restricted to: {s3_prefix}

RESPONSE GUIDELINES:
- Provide concise, clinically relevant information
- Always cite sources (patient records, documents, knowledge base)
- Maintain patient confidentiality - never share PHI inappropriately
- Use patient_context before discussing specific patients
- Use clinic_config to understand available services and providers
- If you don't have necessary information, ask the user for clarification
- Focus on actionable clinical insights

Remember: You are serving {clinic_id} only. All data access is automatically restricted to this clinic.
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
                        "X-Tenant-ID": tenant_id,
                        "X-Clinic-ID": clinic_id,
                        "X-S3-Prefix": s3_prefix
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
