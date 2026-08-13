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
  3. Tier routing:     Model selection per tier via Bedrock Mantle
  4. Cost attribution: Bedrock Projects for per-tier cost tracking,
                       structured usage logging for per-clinic attribution
  5. Gateway headers:  X-Tier, X-Clinic-ID, X-S3-Prefix propagated

Cost attribution uses Amazon Bedrock Projects via the Mantle (OpenAI-compatible)
endpoint. Each tier has a dedicated project whose tags flow into AWS Cost Explorer.
The Strands OpenAIModel provider connects to bedrock-mantle.{region}.api.aws and
passes the project ID on every inference request.

Per-clinic cost attribution is achieved via structured JSON usage logs emitted
after each agent invocation. These logs include clinic_id, tier, model_id, and
token counts (input/output), and can be queried via CloudWatch Logs Insights.
"""

import json
import logging
import os
import re

import requests
from html import unescape
from typing import List, Optional

from .utils import get_ssm_parameter
from .discovery_client import DiscoveryClient
from .memory_hook import MemoryHook
from .guardrail_hook import GuardrailHook, GuardrailInterventionError
from .tools.retrieve_clinic_documents import retrieve_clinic_documents

from mcp.client.streamable_http import streamablehttp_client
from .streamable_http_bearer import streamablehttp_client_with_bearer
from .context import TenantContext
from strands import Agent, tool
from strands_tools import current_time
from strands.models.openai import OpenAIModel
from strands.tools.mcp import MCPClient

logger = logging.getLogger(__name__)

# --- Tier configuration ---

TIER_CONFIG = {
    "basic": {
        "default_model": "mistral.ministral-3-8b-instruct",
        "project_ssm": "/app/healthcare/projects/basic_id",
        "gateway_url_ssm": "/app/healthcare/agentcore/basic_gateway_url",
        "gateway_target": "HealthcareLambda-Basic",
        "web_search": False,
        "guardrail_id_ssm": "/app/healthcare/guardrails/basic_id",
        "guardrail_version_ssm": "/app/healthcare/guardrails/basic_version",
    },
    "premium": {
        "default_model": "openai.gpt-oss-120b",
        "project_ssm": "/app/healthcare/projects/premium_id",
        "gateway_url_ssm": "/app/healthcare/agentcore/premium_gateway_url",
        "gateway_target": "HealthcareLambda-Premium",
        "web_search": True,
        "guardrail_id_ssm": "/app/healthcare/guardrails/premium_id",
        "guardrail_version_ssm": "/app/healthcare/guardrails/premium_version",
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
    tier: str,
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

    if tier == "basic":
        patient_context_section = (
            "- patient_context: Retrieve patient metadata (demographics, conditions, allergies, medications)\n"
            "  * Automatically filtered to your clinic for security\n"
            "  * IMPORTANT: You MUST include request_hour parameter with the current hour (0-23) from current_time.\n"
            "    This is required by the business hours policy. Access is only permitted between 8am-6pm.\n"
            "    Always call current_time first to get the current hour before calling patient_context."
        )
        answering_guidelines = (
            "1. Before accessing patient data, call current_time to get the current hour\n"
            "2. Include request_hour (0-23) when calling patient_context — access is denied outside 8am-6pm\n"
            "3. Search the clinic's documents using retrieve_clinic_documents for relevant clinical information"
        )
    else:
        patient_context_section = (
            "- patient_context: Retrieve patient metadata (demographics, conditions, allergies, medications)\n"
            "  * Automatically filtered to your clinic for security\n"
            "  * Available 24/7 for premium tier users — no business hours restriction."
        )
        answering_guidelines = (
            "1. Use patient_context to look up patient information as needed\n"
            "2. Search the clinic's documents using retrieve_clinic_documents for relevant clinical information"
        )

    return f"""You are a clinical document assistant for a healthcare clinic.

YOUR ASSIGNED CONTEXT:
- Clinic: {clinic_id}
- Tier: {tier}
- User: {user_id} (Role: {role})
- Document Scope: {s3_prefix}

AVAILABLE TOOLS:
- retrieve_clinic_documents: Search knowledge base for clinical documents
  * Automatically filtered to your clinic: {clinic_id}
  * Searches documents under: {s3_prefix}
{patient_context_section}
- clinic_config: Get clinic configuration (specialty, services, hours, providers)
- current_time: Get current date and time
{web_tool_section}
SECURITY RULES:
1. You can ONLY access data for clinic: {clinic_id}
2. All tools automatically filter to your clinic — you cannot access other clinics' data
3. Document searches are restricted to: {s3_prefix}

When answering questions:
{answering_guidelines}

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
        memory_hook: Optional[MemoryHook],
        tier: str = "basic",
        clinic_id: str = "demo-clinic",
        user_id: str = "demo-user",
        role: str = "user",
        s3_prefix: str = "basic-tier/demo-clinic/",
        tools: Optional[List[callable]] = None,
    ):
        config = TIER_CONFIG.get(tier, TIER_CONFIG["basic"])

        # Store tenant context for per-clinic usage logging
        self.tier = tier
        self.clinic_id = clinic_id
        self.user_id = user_id
        self.model_id = config["default_model"]

        # --- Model selection via Bedrock Mantle + Projects (cost attribution per tier) ---
        region = os.environ.get("AWS_REGION", "us-east-1")
        mantle_base_url = f"https://bedrock-mantle.{region}.api.aws/v1"

        # Bedrock API key for Mantle authentication (short-term, auto-refreshed)
        from aws_bedrock_token_generator import provide_token
        try:
            api_key = provide_token(region=region)
        except Exception as e:
            raise RuntimeError(
                f"Failed to generate Bedrock API token: {e}"
            )

        # Load Bedrock Project ID for cost attribution
        project_id = None
        try:
            project_id = get_ssm_parameter(config["project_ssm"])
            logger.info(f"Loaded Bedrock project for tier '{tier}': {project_id}")
        except Exception as e:
            logger.warning(
                f"Bedrock project unavailable for tier '{tier}', "
                f"requests will use the default project: {e}"
            )

        model_id = self.model_id

        client_args = {
            "base_url": mantle_base_url,
            "api_key": api_key,
        }
        if project_id:
            client_args["project"] = project_id

        self.model = OpenAIModel(
            client_args=client_args,
            model_id=model_id,
        )

        # --- Web search (premium only) ---
        web_search_enabled = False
        websearch_tool = None
        if config["web_search"]:
            websearch_tool = _create_websearch_tool()
            web_search_enabled = websearch_tool is not None

        # --- System prompt with tenant context ---
        self.system_prompt = _build_system_prompt(
            tier=tier,
            clinic_id=clinic_id,
            user_id=user_id,
            role=role,
            s3_prefix=s3_prefix,
            web_search_enabled=web_search_enabled,
        )

        # --- Gateway client (MCP) with Bearer token auth (CUSTOM_JWT authorizer) ---
        # The user's JWT (validated by the Runtime's Inbound JWT Authorizer) is
        # forwarded to the Gateway, which validates it against the same Cognito pool.
        discovery = DiscoveryClient()
        gateway_url = discovery.resolve(tier, config["gateway_url_ssm"])
        logger.info(f"Gateway MCP URL: {gateway_url}")

        try:
            self.gateway_client = MCPClient(
                lambda: streamablehttp_client_with_bearer(
                    url=gateway_url,
                    token=TenantContext.get_gateway_token() or "",
                    headers={
                        "X-Tier": tier,
                        "X-Clinic-ID": clinic_id,
                        "X-S3-Prefix": s3_prefix,
                    },
                )
            )

            self._gateway_started = False
        except Exception as e:
            raise RuntimeError(f"Error initializing gateway client: {e}")

        def _ensure_gateway_started():
            """Lazy-start the gateway MCP client on first tool use (avoids cold start timeout)."""
            if not self._gateway_started:
                self.gateway_client.start()
                self._gateway_started = True

        # --- Tool registration ---
        # KB retrieval with clinic_id pre-filled for isolation
        clinic_id_captured = clinic_id
        enforce_hours = tier == "basic"

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
            return retrieve_clinic_documents(query, clinic_id_captured, max_results, enforce_business_hours=enforce_hours)

        # Static gateway tool wrappers — registered statically so the policy engine
        # can enforce at tools/call time with actual arguments (not filtered at list time).
        gateway_ref = self.gateway_client
        gateway_target = config["gateway_target"]
        enforce_business_hours = tier == "basic"

        patient_context_desc = (
            "Retrieve patient metadata (demographics, conditions, allergies, medications). "
            "Filtered to your clinic. IMPORTANT: You MUST include request_hour (0-23) from current_time. "
            "Access is only permitted between 8am-6pm by business hours policy."
            if enforce_business_hours
            else "Retrieve patient metadata (demographics, conditions, allergies, medications). "
            "Filtered to your clinic. Available 24/7 for premium tier."
        )

        @tool(name="patient_context", description=patient_context_desc)
        def patient_context(
            patient_id: str = None,
            list_patients: bool = False,
            limit: int = 20,
            request_hour: int = None,
        ) -> str:
            """Look up patient metadata with clinic isolation.

            Args:
                patient_id: Unique patient identifier (e.g., P12345).
                list_patients: If true, returns all patients for the clinic.
                limit: Max patients to return in list mode.
                request_hour: Current hour 0-23. Required for basic tier business hours policy. Get from current_time.
            """
            args = {}
            if patient_id is not None:
                args["patient_id"] = patient_id
            if list_patients:
                args["list_patients"] = list_patients
                args["limit"] = limit
            # Only pass request_hour for basic tier — premium bypasses business hours policy
            if enforce_business_hours and request_hour is not None:
                args["request_hour"] = request_hour
            try:
                _ensure_gateway_started()
                result = gateway_ref.call_tool_sync(
                    tool_use_id="patient_context_call",
                    name=f"{gateway_target}___patient_context",
                    arguments=args,
                )
                return _extract_gateway_response(result)
            except Exception as e:
                error_msg = str(e)
                if enforce_business_hours and (
                    "denied" in error_msg.lower() or "policy" in error_msg.lower()
                ):
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
                _ensure_gateway_started()
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

        # --- Bedrock Guardrails (tier-specific, via ApplyGuardrail API) ---
        self.guardrail_hook = None
        try:
            guardrail_id = get_ssm_parameter(config["guardrail_id_ssm"])
            guardrail_version = get_ssm_parameter(config["guardrail_version_ssm"])
            self.guardrail_hook = GuardrailHook(
                guardrail_id=guardrail_id,
                guardrail_version=guardrail_version,
                tier=tier,
            )
            logger.info(f"Guardrail loaded for {tier} tier: {guardrail_id} v{guardrail_version}")
        except Exception as e:
            logger.warning(f"Guardrails not available for {tier} tier (non-blocking): {e}")

        self.agent = Agent(
            model=self.model,
            system_prompt=self.system_prompt,
            tools=all_tools,
            hooks=hooks,
        )

    def _log_usage(self, result) -> None:
        """Emit structured JSON log with token usage for per-clinic cost attribution.

        The AgentResult.metrics.accumulated_usage dict contains inputTokens,
        outputTokens, and totalTokens tracked by the Strands SDK across all
        event loop cycles for this invocation.  These logs land in CloudWatch
        and can be queried with Logs Insights to compute per-clinic costs.
        """
        try:
            usage = getattr(getattr(result, "metrics", None), "accumulated_usage", None)
            if not usage:
                return
            logger.info(json.dumps({
                "event": "inference_usage",
                "tier": self.tier,
                "clinic_id": self.clinic_id,
                "user_id": self.user_id,
                "model_id": self.model_id,
                "input_tokens": usage.get("inputTokens", 0),
                "output_tokens": usage.get("outputTokens", 0),
                "total_tokens": usage.get("totalTokens", 0),
            }))
        except Exception as e:
            logger.warning(f"Failed to log usage metrics: {e}")

    def invoke(self, user_query: str) -> str:
        try:
            # Input guardrail check
            if self.guardrail_hook:
                try:
                    self.guardrail_hook.pre_invoke(self.agent, user_query=user_query)
                except GuardrailInterventionError as e:
                    return str(e)

            agent_result = self.agent(user_query)
            self._log_usage(agent_result)
            result = str(agent_result)

            # Output guardrail check
            if self.guardrail_hook:
                result = self.guardrail_hook.post_invoke(self.agent, result)
                if not isinstance(result, str):
                    result = str(result)

            return result
        except GuardrailInterventionError as e:
            return str(e)
        except Exception as e:
            return f"Error invoking agent: {e}"

    async def stream(self, user_query: str):
        try:
            # Input guardrail check
            if self.guardrail_hook:
                try:
                    self.guardrail_hook.pre_invoke(self.agent, user_query=user_query)
                except GuardrailInterventionError as e:
                    yield str(e)
                    return

            # Buffer the full response so output guardrail can filter before sending
            accumulated = ""
            async for event in self.agent.stream_async(user_query):
                if "data" in event:
                    accumulated += event["data"]

            # Log per-clinic usage from the agent's latest metrics
            try:
                metrics = getattr(self.agent, "metrics", None)
                if metrics:
                    latest = getattr(metrics, "latest_agent_invocation", None)
                    if latest and hasattr(latest, "usage"):
                        logger.info(json.dumps({
                            "event": "inference_usage",
                            "tier": self.tier,
                            "clinic_id": self.clinic_id,
                            "user_id": self.user_id,
                            "model_id": self.model_id,
                            "input_tokens": latest.usage.get("inputTokens", 0),
                            "output_tokens": latest.usage.get("outputTokens", 0),
                            "total_tokens": latest.usage.get("totalTokens", 0),
                        }))
            except Exception as e:
                logger.warning(f"Failed to log streaming usage metrics: {e}")

            # Output guardrail check on the full accumulated response
            if self.guardrail_hook and accumulated:
                checked = self.guardrail_hook.post_invoke(self.agent, accumulated)
                if isinstance(checked, str) and checked != accumulated:
                    yield checked
                else:
                    yield accumulated
            else:
                yield accumulated

        except GuardrailInterventionError as e:
            yield str(e)
        except Exception as e:
            yield f"We are unable to process your request at the moment. Error: {e}"
