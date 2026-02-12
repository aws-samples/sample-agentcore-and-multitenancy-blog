from .utils import get_ssm_parameter
from agent_config.memory_hook_provider import MemoryHook
from agent_config.tools.retrieve_clinic_documents import retrieve_clinic_documents  # Import custom tool
from mcp.client.streamable_http import streamablehttp_client
from strands import Agent, tool
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
        tenant_id: str = "basic",
        clinic_id: str = "demo-clinic",
        user_id: str = "demo-user",
        role: str = "user",
        s3_prefix: str = "basic-tier/demo-clinic/",
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
            premium_profile_arn = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
        
                # Get inference profile ARNs from SSM parameters
        try:
            basic_profile_arn = get_ssm_parameter("/app/healthcare/inference_profiles/basic_arn")
            premium_profile_arn = get_ssm_parameter("/app/healthcare/inference_profiles/premium_arn")
        except Exception as e:
            print(f"⚠️ Warning: Could not load inference profiles from SSM: {e}")
            print(f"   Falling back to default model: {bedrock_model_id}")
            basic_profile_arn = bedrock_model_id
            premium_profile_arn = bedrock_model_id
        
        # Map tenant to inference profile
        inference_profile_mapping = {
            "basic": basic_profile_arn,
            "premium": premium_profile_arn,
            "default": basic_profile_arn
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

        gateway_url = get_ssm_parameter("/app/healthcare/agentcore/basic_gateway_url")
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

        # Create wrapper tool using class-based approach (Strands best practice)
        # This properly registers the tool with the framework
        clinic_id_captured = clinic_id  # Capture for closure
        
        @tool(
            name="retrieve_clinic_documents",
            description="Handle document-based, narrative, and conceptual queries using the unstructured knowledge base."
        )
        def retrieve_with_clinic(query: str, max_results: int = 5) -> str:
            """
            Search knowledge base for medical information and clinical documents.
            
            Args:
                query: A question about clinical documents, patient information, medical procedures,
                       or requiring document comprehension and qualitative analysis
                max_results: Number of results to return (default: 5)
            
            Returns:
                Formatted string response from the knowledge base
            """
            return retrieve_clinic_documents(query, clinic_id_captured, max_results)

        self.tools = (
            [
                retrieve_with_clinic,  # Properly decorated tool with clinic_id pre-filled
                current_time,
            ]
            + self.gateway_client.list_tools_sync()  # MCP tools with header propagation
            + tools
        )

        self.memory_hook = memory_hook

        self.agent = Agent(
            model=self.model,
            system_prompt=self.system_prompt,
            tools=self.tools,
            hooks=[self.memory_hook],
        )

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
