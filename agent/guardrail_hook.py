# Copyright 2026 Amazon.com and its affiliates; all rights reserved.
# SPDX-License-Identifier: MIT-0

"""
Bedrock Guardrails hook for Strands Agent.

Since the agent uses OpenAIModel (Mantle endpoint), native BedrockModel guardrail
integration isn't available. This hook uses the ApplyGuardrail API independently
to evaluate both user inputs and model outputs.

The hook is tier-aware: each tier has its own guardrail with different policies.
"""

import json
import logging
import os
from typing import Any

import boto3
from strands.agent.agent_result import AgentResult
from strands.types.content import Message

logger = logging.getLogger(__name__)


class GuardrailHook:
    """
    Strands Agent hook that applies Bedrock Guardrails to inputs and outputs.

    Integrates via the ApplyGuardrail API (model-independent) so it works
    with any model provider including OpenAIModel/Mantle.
    """

    def __init__(self, guardrail_id: str, guardrail_version: str, tier: str = "basic"):
        self.guardrail_id = guardrail_id
        self.guardrail_version = guardrail_version
        self.tier = tier

        region = os.environ.get("AWS_REGION", "us-east-1")
        self.client = boto3.client("bedrock-runtime", region_name=region)

        logger.info(
            f"GuardrailHook initialized: guardrail={guardrail_id}, "
            f"version={guardrail_version}, tier={tier}"
        )

    def _apply_guardrail(self, text: str, source: str) -> dict:
        """
        Call the ApplyGuardrail API.

        Args:
            text: The text to evaluate.
            source: "INPUT" for user prompts, "OUTPUT" for model responses.

        Returns:
            API response dict with action, output, and assessments.
        """
        try:
            response = self.client.apply_guardrail(
                guardrailIdentifier=self.guardrail_id,
                guardrailVersion=self.guardrail_version,
                source=source,
                content=[{"text": {"text": text}}],
            )
            return response
        except Exception as e:
            logger.error(f"GuardrailHook: ApplyGuardrail failed ({source}): {e}")
            # Fail open — don't block the user if the guardrail service is down
            return {"action": "NONE", "outputs": [], "assessments": []}

    def _extract_text_from_message(self, message: Any) -> str:
        """Extract plain text from a Strands message object."""
        if isinstance(message, str):
            return message
        if isinstance(message, dict):
            # Handle {"role": "user", "content": [...]} format
            content = message.get("content", [])
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts = []
                for block in content:
                    if isinstance(block, dict) and "text" in block:
                        parts.append(block["text"])
                    elif isinstance(block, str):
                        parts.append(block)
                return " ".join(parts)
        if hasattr(message, "content"):
            return self._extract_text_from_message(message.content)
        return str(message)

    # --- Strands hook interface ---

    def pre_invoke(self, agent: Any, **kwargs) -> None:
        """Evaluate user input before the model is invoked."""
        # Get the latest user message from the agent's messages
        messages = getattr(agent, "messages", [])
        if not messages:
            return

        last_message = messages[-1]
        if isinstance(last_message, dict) and last_message.get("role") != "user":
            return

        user_text = self._extract_text_from_message(last_message)
        if not user_text.strip():
            return

        result = self._apply_guardrail(user_text, "INPUT")

        if result.get("action") == "GUARDRAIL_INTERVENED":
            # Log the assessment for observability
            assessments = result.get("assessments", [])
            logger.warning(
                f"GuardrailHook: INPUT blocked for {self.tier} tier. "
                f"Assessments: {json.dumps(assessments, default=str)}"
            )

            # Replace the user message with the blocked message
            blocked_text = ""
            for output in result.get("outputs", []):
                if isinstance(output, dict) and "text" in output:
                    blocked_text = output["text"]
                    break

            if not blocked_text:
                blocked_text = (
                    "Your request was blocked by our safety policy. "
                    "Please rephrase your question."
                )

            # Raise to stop the agent from processing
            raise GuardrailInterventionError(blocked_text, "INPUT", assessments)

    def post_invoke(self, agent: Any, result: Any, **kwargs) -> Any:
        """Evaluate model output after the model responds."""
        # Extract the response text
        response_text = ""
        if isinstance(result, str):
            response_text = result
        elif isinstance(result, AgentResult):
            response_text = str(result)
        elif hasattr(result, "content"):
            response_text = self._extract_text_from_message(result)
        else:
            response_text = str(result)

        if not response_text.strip():
            return result

        guardrail_result = self._apply_guardrail(response_text, "OUTPUT")

        if guardrail_result.get("action") == "GUARDRAIL_INTERVENED":
            assessments = guardrail_result.get("assessments", [])
            logger.warning(
                f"GuardrailHook: OUTPUT blocked/modified for {self.tier} tier. "
                f"Assessments: {json.dumps(assessments, default=str)}"
            )

            # Return the guardrail's modified/blocked output
            for output in guardrail_result.get("outputs", []):
                if isinstance(output, dict) and "text" in output:
                    return output["text"]

            return (
                "The response was blocked by our safety policy. "
                "Please try a different question."
            )

        return result


class GuardrailInterventionError(Exception):
    """Raised when a guardrail blocks the input."""

    def __init__(self, message: str, source: str, assessments: list):
        super().__init__(message)
        self.source = source
        self.assessments = assessments
