from .utils import get_ssm_parameter
from agent_config_premium.memory_hook_provider import MemoryHook
from agent_config_premium.tools.retrieve_clinic_documents import retrieve_clinic_documents  # Import custom tool
from mcp.client.streamable_http import streamablehttp_client
from strands import Agent
from strands_tools import current_time  # Keep current_time
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
        tenant_id: str = "premium",
        clinic_id: str = "demo-clinic",
        user_id: str = "demo-user",
        role: str = "user",
        s3_prefix: str = "premium-tier/demo-clinic/",
        guardrail_id: str = None,
    ):
        # Get inference profile ARNs from SSM parameters
        # These are application-defined profiles created by scripts/create_inference_profiles.py
        # for cost allocation and tier-specific tracking
        try:
            basic_profile_arn = get_ssm_parameter("/app/healthcare/inference_profiles/basic_arn")
            premium_profile_arn = get_ssm_parameter("/app/healthcare/inference_profiles/premium_arn")
            print(f"✅ Loaded inference profiles from SSM")
        except Exception as e:
            print(f"⚠️ Warning: Could not load inference profiles from SSM: {e}")
            print(f"   Falling back to system-defined profiles")
            # Fallback to system-defined profiles if application profiles don't exist
            basic_profile_arn = "us.amazon.nova-micro-v1:0"
            premium_profile_arn = "us.amazon.nova-2-lite-v1:0"
        
        # Map tenant to inference profile
        inference_profile_mapping = {
            "basic": basic_profile_arn,
            "premium": premium_profile_arn,
            "default": basic_profile_arn
        }
        
        # Use inference profile based on tenant, fallback to original model
        self.model_id = inference_profile_mapping.get(tenant_id, bedrock_model_id)
        print(f"🔍 DEBUG: Tenant '{tenant_id}' using model: {self.model_id}")
        
        # Build model configuration with guardrail and web grounding
        model_config = {
            "model_id": self.model_id,
            "tool_config": {
                "tools": [{
                    "systemTool": {
                        "name": "nova_grounding"
                    }
                }]
            }
        }
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
You are an advanced clinical document assistant for a healthcare clinic with premium analytics capabilities and web search access.

YOUR ASSIGNED CONTEXT:
- Clinic: {clinic_id}
- Tier: {tenant_id} (Premium)
- User: {user_id} (Role: {role})
- Document Scope: {s3_prefix}

AVAILABLE TOOLS:
- retrieve_clinic_documents: Search knowledge base for medical information and clinical documents
  * Automatically filtered to your clinic: {clinic_id}
  * Searches documents under your clinic's scope: {s3_prefix}
  * Returns relevant documents with context from the knowledge base
- patient_context: Retrieve patient metadata (demographics, conditions, allergies, medications, visit history)
  * Use patient_id for single patient lookup
  * Use list_patients=true to get all patients for the clinic
  * Automatically filtered to your clinic for security
- clinic_config: Get clinic configuration (specialty, services, hours, providers)
  * Defaults to your clinic if no clinic_id specified
- current_time: Get current date and time
- nova_grounding: Search external medical research and clinical guidelines (Premium feature)

WEB SEARCH CAPABILITY (Premium Feature):
You have access to web search for medical research from trusted sources including:
- NIH (nih.gov)
- CDC (cdc.gov)
- WHO (who.int)
- PubMed (pubmed.ncbi.nlm.nih.gov)
- Medical journals and .edu institutions

When answering questions:
1. First check patient_context for patient background
2. Search the clinic's documents using retrieve_clinic_documents for relevant clinical information
3. If additional context is needed, use web search (nova_grounding) for current medical guidelines
4. Always cite sources with URLs for web-sourced information
5. Clearly distinguish between clinic documents and external sources

CRITICAL SECURITY RULES:
1. You can ONLY access data for clinic: {clinic_id}
2. All tools automatically filter to your clinic - you cannot access other clinics' data
3. Patient data is protected - only accessible within your clinic scope
4. Document searches are restricted to: {s3_prefix}
5. Web search results should be from reputable medical sources only

RESPONSE GUIDELINES:
- Provide comprehensive, clinically relevant analysis
- Always cite sources (patient records, documents, knowledge base, web)
- For web-sourced information, include URLs and source domains
- Maintain patient confidentiality at all times
- Use patient_context before discussing specific patients
- Use clinic_config to understand available services and providers
- If you don't have necessary information, ask the user for clarification
- Focus on actionable clinical insights with supporting evidence

Remember: You are serving {clinic_id} with premium-tier capabilities including web search. All data access is automatically restricted to this clinic.
"""
        )

        gateway_url = get_ssm_parameter("/app/healthcare/agentcore/premium_gateway_url")
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

        # Create wrapper for retrieve_clinic_documents with clinic_id pre-filled
        def retrieve_with_clinic(query: str, max_results: int = 5) -> str:
            """Wrapper that automatically provides clinic_id"""
            return retrieve_clinic_documents(query, clinic_id, max_results)
        
        # Copy tool metadata
        retrieve_with_clinic.__name__ = 'retrieve_clinic_documents'
        retrieve_with_clinic.__doc__ = retrieve_clinic_documents.__doc__

        self.tools = (
            [
                retrieve_with_clinic,  # Custom tool with clinic_id pre-filled
                current_time,
            ]
            + self.gateway_client.list_tools_sync()  # Use tools directly
            + tools
        )

        self.memory_hook = memory_hook

        # Build hooks list - only include memory_hook if it's not None
        hooks = [self.memory_hook] if self.memory_hook else []

        self.agent = Agent(
            model=self.model,
            system_prompt=self.system_prompt,
            tools=self.tools,
            hooks=hooks,
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
