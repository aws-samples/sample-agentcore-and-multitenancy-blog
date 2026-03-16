import json
from .utils import get_ssm_parameter
from agent_config.memory_hook_provider import MemoryHook
from agent_config.tools.retrieve_clinic_documents import retrieve_clinic_documents  # Import custom tool
from mcp.client.streamable_http import streamablehttp_client
from strands import Agent, tool
from strands_tools import current_time
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient
from typing import List


def _extract_gateway_response(result) -> str:
    """Extract clean text from an MCP gateway call result and unwrap Lambda envelope."""
    raw = ""
    try:
        if isinstance(result, dict):
            content = result.get("content", result)
            if isinstance(content, list):
                text_parts = []
                for block in content:
                    if isinstance(block, dict) and "text" in block:
                        text_parts.append(str(block["text"]))
                    elif hasattr(block, "text"):
                        text_parts.append(str(block.text))
                    else:
                        text_parts.append(str(block))
                raw = "\n".join(text_parts)
            elif isinstance(content, str):
                raw = content
            else:
                raw = str(content)
        elif hasattr(result, "content") and isinstance(result.content, list):
            text_parts = []
            for block in result.content:
                if hasattr(block, "text"):
                    text_parts.append(block.text)
            raw = "\n".join(text_parts) if text_parts else str(result.content)
        else:
            raw = str(result)
    except Exception:
        raw = str(result)

    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict) and "body" in parsed:
            body = parsed["body"]
            if isinstance(body, str):
                body = json.loads(body)
            return json.dumps(body)
    except (json.JSONDecodeError, TypeError, KeyError):
        pass

    return raw


class HealthcareAI:
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

        # Static gateway tool wrappers — bypass list_tools_sync() which gets
        # filtered by the policy engine in ENFORCE mode. Register tools statically
        # and let the policy engine enforce at tools/call time with actual arguments.
        gateway_client_ref = self.gateway_client
        gateway_target = "HealthcareLambda-Basic"

        @tool(
            name="patient_context",
            description=(
                "Retrieve structured patient metadata including demographics, medical conditions, "
                "allergies, medications, and visit history. Automatically filtered to the requesting "
                "clinic for security."
            ),
        )
        def patient_context(
            patient_id: str = None,
            list_patients: bool = False,
            limit: int = 20,
            request_hour: int = None,
        ) -> str:
            """Look up patient metadata with clinic isolation.

            Args:
                patient_id: Unique patient identifier (e.g., P12345).
                list_patients: If true, returns paginated list of all patients for the clinic.
                limit: Number of patients to return in list (max 100). Only used when list_patients=true.
                request_hour: Current hour 0-23 for policy enforcement.

            Returns:
                Patient metadata or error message.
            """
            args = {}
            if patient_id is not None:
                args["patient_id"] = patient_id
            if list_patients:
                args["list_patients"] = list_patients
                args["limit"] = limit
            if request_hour is not None:
                args["request_hour"] = request_hour
            try:
                result = gateway_client_ref.call_tool_sync(
                    tool_use_id="patient_context_call",
                    name=f"{gateway_target}___patient_context",
                    arguments=args,
                )
                return _extract_gateway_response(result)
            except Exception as e:
                return f"Error accessing patient data: {e}"

        @tool(
            name="clinic_config",
            description=(
                "Retrieve clinic-specific configuration including specialty, available services, "
                "operating hours, and provider list."
            ),
        )
        def clinic_config(clinic_id_param: str = None) -> str:
            """Get clinic configuration and capabilities.

            Args:
                clinic_id_param: Specific clinic identifier. Defaults to requesting user's clinic.

            Returns:
                Clinic configuration data.
            """
            args = {}
            if clinic_id_param is not None:
                args["clinic_id"] = clinic_id_param
            try:
                result = gateway_client_ref.call_tool_sync(
                    tool_use_id="clinic_config_call",
                    name=f"{gateway_target}___clinic_config",
                    arguments=args,
                )
                return _extract_gateway_response(result)
            except Exception as e:
                return f"Error accessing clinic configuration: {e}"

        self.policy_restricted_tools = set()

        self.tools = (
            [
                retrieve_with_clinic,
                current_time,
            ]
            + [patient_context, clinic_config]
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
