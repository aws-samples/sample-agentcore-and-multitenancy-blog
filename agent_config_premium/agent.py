import os
import logging

from .utils import get_ssm_parameter
from agent_config_premium.memory_hook_provider import MemoryHook
from agent_config_premium.tools.retrieve_clinic_documents import retrieve_clinic_documents  # Import custom tool
from mcp.client.streamable_http import streamablehttp_client
from strands import Agent, tool
from strands_tools import current_time  # Keep current_time
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient
from typing import List

logger = logging.getLogger(__name__)


def _create_websearch_tool():
    """Create a DuckDuckGo-based web search tool using requests + HTML parsing.
    
    Uses the DuckDuckGo HTML endpoint directly — no external SDK or API key needed.
    Returns the web_search tool function, or None if creation fails.
    The agent continues to work without web search if it fails.
    """
    import re
    import requests
    from html import unescape

    def _ddg_search(query: str, max_results: int = 3) -> list:
        """Query DuckDuckGo HTML endpoint and parse results."""
        resp = requests.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        resp.raise_for_status()
        html = resp.text

        results = []
        # Each result block lives inside <div class="result ...">
        for block in re.finditer(
            r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?'
            r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
            html,
            re.DOTALL,
        ):
            raw_url, raw_title, raw_snippet = block.group(1), block.group(2), block.group(3)
            # DuckDuckGo wraps URLs in a redirect; extract the actual URL
            url_match = re.search(r'uddg=([^&]+)', raw_url)
            url = requests.utils.unquote(url_match.group(1)) if url_match else raw_url
            title = unescape(re.sub(r'<[^>]+>', '', raw_title)).strip()
            snippet = unescape(re.sub(r'<[^>]+>', '', raw_snippet)).strip()
            results.append({"title": title, "href": url, "body": snippet})
            if len(results) >= max_results:
                break
        return results

    try:
        @tool(
            name="web_search",
            description="Search the web for current medical research, guidelines, drug information, and clinical best practices."
        )
        def web_search(keywords: str) -> str:
            """
            Search the web using DuckDuckGo for medical and clinical information.

            Args:
                keywords: Search query for medical research, guidelines, or clinical information.

            Returns:
                Formatted string with top 3 search results including titles, URLs, and snippets.
            """
            try:
                results = _ddg_search(keywords, max_results=3)
                if not results:
                    return "No web search results found for the given query."
                formatted = []
                for r in results:
                    formatted.append(
                        f"Title: {r.get('title', 'N/A')}\n"
                        f"URL: {r.get('href', 'N/A')}\n"
                        f"Snippet: {r.get('body', 'N/A')}"
                    )
                return "\n\n---\n\n".join(formatted)
            except Exception as e:
                logger.warning(f"⚠️ Web search failed for query '{keywords}': {e}")
                return f"Web search is temporarily unavailable: {e}"

        logger.info("✅ DuckDuckGo web search tool created successfully (requests-based)")
        return web_search
    except Exception as e:
        logger.warning(f"⚠️ Failed to create web search tool: {e}")
        return None


class CustomerSupport:
    def __init__(
        self,
        bearer_token: str,
        memory_hook: MemoryHook,
        bedrock_model_id: str = "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
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
        
                # Get inference profile ARNs from SSM parameters
        try:
            basic_profile_arn = get_ssm_parameter("/app/healthcare/inference_profiles/basic_arn")
            premium_profile_arn = get_ssm_parameter("/app/healthcare/inference_profiles/premium_arn")
        except Exception as e:
            print(f"⚠️ Warning: Could not load inference profiles from SSM: {e}")
            print(f"   Falling back to default model: {bedrock_model_id}")
            basic_profile_arn = bedrock_model_id
            premium_profile_arn = bedrock_model_id
        
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
        
        # Load DuckDuckGo web search (premium feature — no API key needed)
        self.websearch_tool = _create_websearch_tool()
        web_search_enabled = self.websearch_tool is not None
        
        self.system_prompt = (
            system_prompt
            if system_prompt
            else f"""
You are an advanced clinical document assistant for a healthcare clinic with premium analytics capabilities{' and web search access' if web_search_enabled else ''}.

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
  * IMPORTANT: You MUST include request_hour parameter with the current hour (0-23) from current_time.
    This is required by the business hours policy. Access is only permitted between 8am-6pm.
    Always call current_time first to get the current hour before calling patient_context.
- clinic_config: Get clinic configuration (specialty, services, hours, providers)
  * Defaults to your clinic if no clinic_id specified
- current_time: Get current date and time
{'''- web_search: Search the web for current medical research, guidelines, and clinical information (Premium feature)
  * Returns top 3 results with titles, URLs, and content snippets
  * Use for current medical guidelines and research''' if web_search_enabled else ''}

{'WEB SEARCH CAPABILITY (Premium Feature):' if web_search_enabled else ''}
{'You have access to web search via web_search for medical research from trusted sources including:' if web_search_enabled else ''}
{'- NIH (nih.gov)' if web_search_enabled else ''}
{'- CDC (cdc.gov)' if web_search_enabled else ''}
{'- WHO (who.int)' if web_search_enabled else ''}
{'- PubMed (pubmed.ncbi.nlm.nih.gov)' if web_search_enabled else ''}
{'- Medical journals and .edu institutions' if web_search_enabled else ''}

When answering questions:
1. Before accessing patient data, call current_time to get the current hour
2. Include request_hour (0-23) when calling patient_context — access is denied outside 8am-6pm
3. Search the clinic's documents using retrieve_clinic_documents for relevant clinical information
{'4. If additional context is needed, use web_search for current medical guidelines' if web_search_enabled else '4. If additional context is needed beyond clinic documents, let the user know'}
5. Always cite sources with URLs for web-sourced information
6. Clearly distinguish between clinic documents and external sources

CRITICAL SECURITY RULES:
1. You can ONLY access data for clinic: {clinic_id}
2. All tools automatically filter to your clinic - you cannot access other clinics' data
3. Patient data is protected - only accessible within your clinic scope
4. Document searches are restricted to: {s3_prefix}
{'5. Web search results should be from reputable medical sources only' if web_search_enabled else ''}

RESPONSE GUIDELINES:
- Provide comprehensive, clinically relevant analysis
- Always cite sources (patient records, documents, knowledge base{', web' if web_search_enabled else ''})
{'- For web-sourced information, include URLs and source domains' if web_search_enabled else ''}
- Maintain patient confidentiality at all times
- Use patient_context before discussing specific patients
- Use clinic_config to understand available services and providers
- If you don't have necessary information, ask the user for clarification
- Focus on actionable clinical insights with supporting evidence

Remember: You are serving {clinic_id} with premium-tier capabilities{' including web search' if web_search_enabled else ''}. All data access is automatically restricted to this clinic.
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

        # Build tools list — conditionally include web_search if available
        base_tools = [
            retrieve_with_clinic,  # Properly decorated tool with clinic_id pre-filled
            current_time,
        ]
        
        if self.websearch_tool:
            base_tools.append(self.websearch_tool)
        
        # Static gateway tool wrappers — bypass list_tools_sync() which gets
        # filtered by the policy engine in ENFORCE mode (default-deny strips
        # tools with conditional permits during listing since there's no input).
        # Instead, register tools statically and let the policy engine enforce
        # at tools/call time with actual arguments.
        gateway_client_ref = self.gateway_client
        gateway_target = "HealthcareLambda-Premium"

        @tool(
            name="patient_context",
            description=(
                "Retrieve structured patient metadata including demographics, medical conditions, "
                "allergies, medications, and visit history. Automatically filtered to the requesting "
                "clinic for security. IMPORTANT: You MUST include request_hour (0-23) from current_time. "
                "Access is only permitted between 8am-6pm by business hours policy."
            ),
        )
        def patient_context(
            patient_id: str = None,
            list_patients: bool = False,
            limit: int = 20,
            request_hour: int = None,
        ) -> str:
            """Look up patient metadata with clinic isolation and business hours enforcement.

            Args:
                patient_id: Unique patient identifier (e.g., P12345).
                list_patients: If true, returns paginated list of all patients for the clinic.
                limit: Number of patients to return in list (max 100). Only used when list_patients=true.
                request_hour: Current hour 0-23. Required for business hours policy. Get from current_time.

            Returns:
                Patient metadata or policy denial message.
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
                return str(result.content)
            except Exception as e:
                error_msg = str(e)
                if "denied" in error_msg.lower() or "policy" in error_msg.lower():
                    return (
                        "🛡️ Access denied by business hours policy. "
                        "Patient data is only available between 8:00 AM and 6:00 PM. "
                        "Please try again during business hours."
                    )
                return f"Error accessing patient data: {error_msg}"

        @tool(
            name="clinic_config",
            description=(
                "Retrieve clinic-specific configuration including specialty, available services, "
                "operating hours, and provider list. Use this to understand clinic capabilities."
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
                return str(result.content)
            except Exception as e:
                return f"Error accessing clinic configuration: {e}"

        self.policy_restricted_tools = set()  # No longer detected at list time

        self.tools = (
            base_tools
            + [patient_context, clinic_config]
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
