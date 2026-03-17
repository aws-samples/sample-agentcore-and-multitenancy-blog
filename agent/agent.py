# Copyright 2026 Amazon.com and its affiliates; all rights reserved.
# SPDX-License-Identifier: MIT-0

"""
Consolidated healthcare agent — single class serving both basic and premium tiers.

Tier differences are handled via configuration, not code duplication:
  - Basic:   Nova Micro model, document search + gateway tools
  - Premium: Claude Sonnet model, all basic tools + web search

Multi-tenancy concerns addressed:
  1. Data isolation:   KB metadata filtering by clinic_id
  2. Memory isolation: Hierarchical actor_id in MemoryHook
  3. Tier routing:     Inference profile selection per tenant
  4. Cost attribution: Inference profiles for per-tenant cost tracking
  5. Gateway headers:  X-Tenant-ID, X-Clinic-ID, X-S3-Prefix propagated
"""

import json
import logging
import re

import requests
from html import unescape
from typing import List, Optional

from .utils import get_ssm_parameter
from .memory_hook import MemoryHook
from .tools.retrieve_clinic_documents import retrieve_clinic_documents

from mcp.client.streamable_http import streamablehttp_client
from strands import Agent, tool
from strands_tools import current_time
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient

logger = logging.getLogger(__name__)

# --- Tier configuration ---

TIER_CONFIG = {
    "basic": {
        "default_model": "us.amazon.nova-micro-v1:0",
        "inference_profile_ssm": "/app/healthcare/inference_profiles/basic_arn",
        "gateway_url_ssm": "/app/healthcare/agentcore/basic_gateway_url",
        "gateway_target": "HealthcareLambda-Basic",
        "web_search": False,
    },
    "premium": {
        "default_model": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        "inference_profile_ssm": "/app/healthcare/inference_profiles/premium_arn",
        "gateway_url_ssm": "/app/healthcare/agentcore/premium_gateway_url",
        "gateway_target": "HealthcareLambda-Premium",
        "web_search": True,
    },
}


def _extract_gateway_response(result) -> str:
    """Extract clean text from an MCP gateway call result and unwrap Lambda envelope.

    call_tool_sync returns a dict with keys: status, toolUseId, content.
    content is a list of blocks, each a dict with a 'text' key containing
    the Lambda response as a JSON string with statusCode/body envelope.
    """
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

    # Unwrap Lambda statusCode/body envelope if present
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


def _create_websearch_tool():
    """Create a DuckDuckGo web search tool (premium tier only, no API key needed)."""

    def _ddg_search(query: str, max_results: int = 3) -> list:
        resp = requests.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        resp.raise_for_status()
        results = []
        for block in re.finditer(
            r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?'
            r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
            resp.text,
            re.DOTALL,
        ):
            raw_url, raw_title, raw_snippet = block.group(1), block.group(2), block.group(3)
            url_match = re.search(r"uddg=([^&]+)", raw_url)
            url = requests.utils.unquote(url_match.group(1)) if url_match else raw_url
            title = unescape(re.sub(r"<[^>]+>", "", raw_title)).strip()
            snippet = unescape(re.sub(r"<[^>]+>", "", raw_snippet)).strip()
            results.append({"title": title, "href": url, "body": snippet})
            if len(results) >= max_results:
                break
        return results

    try:

        @tool(
            name="web_search",
            description="Search the web for current medical research, guidelines, drug information, and clinical best practices.",
        )
        def web_search(keywords: str) -> str:
            """Search the web for medical and clinical information.

            Args:
                keywords: Search query for medical research, guidelines, or clinical information.

            Returns:
                Formatted string with top 3 search results.
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
                logger.warning(f"Web search failed for query '{keywords}': {e}")
                return f"Web search is temporarily unavailable: {e}"

        logger.info("DuckDuckGo web search tool created successfully")
        return web_search
    except Exception as e:
        logger.warning(f"Failed to create web search tool: {e}")
        return None


def _build_system_prompt(
    tenant_id: str,
    clinic_id: str,
    user_id: str,
    role: str,
    s3_prefix: str,
    web_search_enabled: bool,
) -> str:
    """Build a tier-appropriate system prompt with tenant context baked in."""
    web_tool_section = ""
    if web_search_enabled:
        web_tool_section = (
            "- web_search: Search the web for current medical research, guidelines, "
            "and clinical information (Premium feature)\n"
        )

    return f"""You are a clinical document assistant for a healthcare clinic.

YOUR ASSIGNED CONTEXT:
- Clinic: {clinic_id}
- Tier: {tenant_id}
- User: {user_id} (Role: {role})
- Document Scope: {s3_prefix}

AVAILABLE TOOLS:
- retrieve_clinic_documents: Search knowledge base for clinical documents
  * Automatically filtered to your clinic: {clinic_id}
  * Searches documents under: {s3_prefix}
- patient_context: Retrieve patient metadata (demographics, conditions, allergies, medications)
  * Automatically filtered to your clinic for security
  * IMPORTANT: You MUST include request_hour parameter with the current hour (0-23) from current_time.
    This is required by the business hours policy. Access is only permitted between 8am-6pm.
    Always call current_time first to get the current hour before calling patient_context.
- clinic_config: Get clinic configuration (specialty, services, hours, providers)
- current_time: Get current date and time
{web_tool_section}
SECURITY RULES:
1. You can ONLY access data for clinic: {clinic_id}
2. All tools automatically filter to your clinic — you cannot access other clinics' data
3. Document searches are restricted to: {s3_prefix}

When answering questions:
1. Before accessing patient data, call current_time to get the current hour
2. Include request_hour (0-23) when calling patient_context — access is denied outside 8am-6pm
3. Search the clinic's documents using retrieve_clinic_documents for relevant clinical information

RESPONSE GUIDELINES:
- Provide concise, clinically relevant information
- Always cite sources (patient records, documents, knowledge base)
- Use patient_context before discussing specific patients
- If you don't have necessary information, ask the user for clarification
"""


class HealthcareAgent:
    """
    Single agent class serving both basic and premium tiers.

    Tier-specific behavior is driven by TIER_CONFIG, not separate codepaths.
    """

    def __init__(
        self,
        bearer_token: str,
        memory_hook: Optional[MemoryHook],
        tenant_id: str = "basic",
        clinic_id: str = "demo-clinic",
        user_id: str = "demo-user",
        role: str = "user",
        s3_prefix: str = "basic-tier/demo-clinic/",
        tools: Optional[List[callable]] = None,
    ):
        config = TIER_CONFIG.get(tenant_id, TIER_CONFIG["basic"])

        # --- Model selection via inference profiles (cost attribution per tenant) ---
        try:
            model_id = get_ssm_parameter(config["inference_profile_ssm"])
            logger.info(f"Loaded inference profile for tier '{tenant_id}': {model_id}")
        except Exception as e:
            model_id = config["default_model"]
            logger.warning(f"Inference profile unavailable, using default: {model_id} ({e})")

        self.model = BedrockModel(model_id=model_id)

        # --- Web search (premium only) ---
        web_search_enabled = False
        websearch_tool = None
        if config["web_search"]:
            websearch_tool = _create_websearch_tool()
            web_search_enabled = websearch_tool is not None

        # --- System prompt with tenant context ---
        self.system_prompt = _build_system_prompt(
            tenant_id=tenant_id,
            clinic_id=clinic_id,
            user_id=user_id,
            role=role,
            s3_prefix=s3_prefix,
            web_search_enabled=web_search_enabled,
        )

        # --- Gateway client (MCP) with tenant headers ---
        gateway_url = get_ssm_parameter(config["gateway_url_ssm"])
        logger.info(f"Gateway MCP URL: {gateway_url}")

        try:
            self.gateway_client = MCPClient(
                lambda: streamablehttp_client(
                    gateway_url,
                    headers={
                        "Authorization": f"Bearer {bearer_token}",
                        "X-Tenant-ID": tenant_id,
                        "X-Clinic-ID": clinic_id,
                        "X-S3-Prefix": s3_prefix,
                    },
                )
            )
            self.gateway_client.start()
        except Exception as e:
            raise RuntimeError(f"Error initializing gateway client: {e}")

        # --- Tool registration ---
        # KB retrieval with clinic_id pre-filled for isolation
        clinic_id_captured = clinic_id

        @tool(
            name="retrieve_clinic_documents",
            description="Search the knowledge base for clinical documents filtered to your clinic.",
        )
        def retrieve_with_clinic(query: str, max_results: int = 5) -> str:
            """Search knowledge base for clinical documents.

            Args:
                query: Question about clinical documents or patient information.
                max_results: Number of results to return (default: 5).
            """
            return retrieve_clinic_documents(query, clinic_id_captured, max_results)

        # Static gateway tool wrappers — registered statically so the policy engine
        # can enforce at tools/call time with actual arguments (not filtered at list time).
        gateway_ref = self.gateway_client
        gateway_target = config["gateway_target"]

        @tool(
            name="patient_context",
            description=(
                "Retrieve patient metadata (demographics, conditions, allergies, medications). "
                "Filtered to your clinic. IMPORTANT: You MUST include request_hour (0-23) from current_time. "
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
                list_patients: If true, returns all patients for the clinic.
                limit: Max patients to return in list mode.
                request_hour: Current hour 0-23. Required for business hours policy. Get from current_time.
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
                result = gateway_ref.call_tool_sync(
                    tool_use_id="patient_context_call",
                    name=f"{gateway_target}___patient_context",
                    arguments=args,
                )
                return _extract_gateway_response(result)
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
            description="Retrieve clinic configuration including specialty, services, hours, and providers.",
        )
        def clinic_config(clinic_id_param: str = None) -> str:
            """Get clinic configuration.

            Args:
                clinic_id_param: Specific clinic ID. Defaults to your clinic.
            """
            args = {}
            if clinic_id_param is not None:
                args["clinic_id"] = clinic_id_param
            try:
                result = gateway_ref.call_tool_sync(
                    tool_use_id="clinic_config_call",
                    name=f"{gateway_target}___clinic_config",
                    arguments=args,
                )
                return _extract_gateway_response(result)
            except Exception as e:
                return f"Error accessing clinic configuration: {e}"

        # Assemble tool list
        all_tools = [retrieve_with_clinic, current_time, patient_context, clinic_config]
        if websearch_tool:
            all_tools.append(websearch_tool)
        if tools:
            all_tools.extend(tools)

        # --- Create Strands Agent ---
        hooks = [memory_hook] if memory_hook else []
        self.agent = Agent(
            model=self.model,
            system_prompt=self.system_prompt,
            tools=all_tools,
            hooks=hooks,
        )

    def invoke(self, user_query: str) -> str:
        try:
            return str(self.agent(user_query))
        except Exception as e:
            return f"Error invoking agent: {e}"

    async def stream(self, user_query: str):
        try:
            async for event in self.agent.stream_async(user_query):
                if "data" in event:
                    yield event["data"]
        except Exception as e:
            yield f"We are unable to process your request at the moment. Error: {e}"
