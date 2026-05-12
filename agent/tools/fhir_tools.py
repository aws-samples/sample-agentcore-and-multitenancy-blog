# Copyright 2026 Amazon.com and its affiliates; all rights reserved.
# SPDX-License-Identifier: MIT-0

"""
FHIR tool wrappers for the Healthcare Agent.

Uses AgentCore Identity's On-Behalf-Of (OBO) token exchange to obtain
a scoped access token for the FHIR resource server. The flow:

  1. Agent has the user's inbound JWT (validated by Runtime's Inbound JWT Authorizer)
  2. Calls GetWorkloadAccessTokenForJWT → wraps user identity into a workload token
  3. Calls GetResourceOauth2Token with ON_BEHALF_OF_TOKEN_EXCHANGE → gets OBO token
  4. Passes the OBO token as Bearer to the FHIR API Gateway

The OBO token carries both the agent's identity and the user's identity,
enabling the FHIR service to enforce fine-grained, zero-trust authorization.

Demonstrates:
  - On-Behalf-Of token exchange (RFC 8693) via AgentCore Identity
  - Inbound-to-outbound auth propagation with scoped tokens
  - Tenant isolation at the FHIR layer (clinic-scoped queries)
  - MCP composability (agent calls multiple downstream services)
"""

import json
import logging
import os
from typing import Optional

import boto3
import requests
from strands import tool

logger = logging.getLogger(__name__)

# Cache the AgentCore client (reused across tool invocations)
_agentcore_client = None


def _get_agentcore_client():
    """Get or create the bedrock-agentcore client for identity operations."""
    global _agentcore_client
    if _agentcore_client is None:
        region = os.environ.get("AWS_REGION", "us-east-1")
        _agentcore_client = boto3.client("bedrock-agentcore", region_name=region)
    return _agentcore_client


def _exchange_token_obo(
    user_jwt: str,
    workload_name: str,
    provider_name: str,
    scopes: list[str],
) -> Optional[str]:
    """
    Perform On-Behalf-Of token exchange via AgentCore Identity.

    Steps:
      1. GetWorkloadAccessTokenForJWT — wraps user JWT into workload access token
      2. GetResourceOauth2Token — exchanges workload token for scoped OBO token

    Args:
        user_jwt: The inbound user JWT (from Cognito)
        workload_name: Registered workload name in AgentCore Identity
        provider_name: The OBO credential provider name
        scopes: OAuth scopes to request for the FHIR resource server

    Returns:
        The OBO access token, or None if exchange fails.
    """
    client = _get_agentcore_client()

    try:
        # Step 1: Get workload access token (wraps user identity)
        workload_response = client.get_workload_access_token_for_jwt(
            workloadName=workload_name,
            userToken=user_jwt,
        )
        workload_token = workload_response["workloadAccessToken"]
        logger.info("OBO Step 1: Obtained workload access token")

        # Step 2: Exchange for OBO token targeting FHIR resource server
        obo_response = client.get_resource_oauth2_token(
            resourceCredentialProviderName=provider_name,
            oauth2Flow="ON_BEHALF_OF_TOKEN_EXCHANGE",
            scopes=scopes,
            workloadIdentityToken=workload_token,
        )

        access_token = obo_response.get("accessToken")
        if access_token:
            logger.info("OBO Step 2: Obtained scoped OBO token for FHIR")
            return access_token

        # Check if authorization is still in progress
        session_status = obo_response.get("sessionStatus")
        if session_status == "IN_PROGRESS":
            logger.warning("OBO token exchange requires user authorization (unexpected for OBO flow)")
            return None

        logger.warning(f"OBO token exchange returned no access token. Status: {session_status}")
        return None

    except Exception as e:
        logger.error(f"OBO token exchange failed: {e}")
        return None


def _call_fhir_api(fhir_api_url: str, token: str, tool_name: str, params: dict) -> dict:
    """
    Call the FHIR MCP API Gateway with Bearer token auth.

    Args:
        fhir_api_url: The FHIR API Gateway endpoint URL
        token: OBO access token (or fallback user JWT)
        tool_name: FHIR tool to invoke
        params: Tool parameters

    Returns:
        Parsed JSON response from the FHIR Lambda
    """
    try:
        resp = requests.post(
            fhir_api_url,
            json={"tool": tool_name, "params": params},
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=20,
        )

        if resp.status_code == 401:
            return {"error": "Authentication failed — invalid or expired token"}
        if resp.status_code == 403:
            return {"error": "Access denied — insufficient permissions"}

        resp.raise_for_status()
        return resp.json()

    except requests.exceptions.Timeout:
        return {"error": "FHIR service request timed out"}
    except requests.exceptions.RequestException as e:
        logger.warning(f"FHIR API call failed: {e}")
        return {"error": f"FHIR service unavailable: {str(e)}"}


def create_fhir_tools(fhir_api_url: str, get_token_fn, obo_config: dict = None):
    """
    Create FHIR tool functions with OBO token exchange.

    Args:
        fhir_api_url: The FHIR MCP API Gateway endpoint URL
        get_token_fn: Callable that returns the current user's JWT
        obo_config: OBO configuration dict with keys:
            - workload_name: Registered workload name
            - provider_name: OBO credential provider name
            - scopes: List of scopes to request
            If None, falls back to passing the raw JWT (dev mode).

    Returns:
        List of tool functions to register with the agent
    """

    def _get_fhir_token() -> Optional[str]:
        """Get a token for FHIR access — OBO exchange or fallback to raw JWT."""
        user_jwt = get_token_fn()
        if not user_jwt:
            return None

        # Attempt OBO token exchange if configured
        if obo_config:
            obo_token = _exchange_token_obo(
                user_jwt=user_jwt,
                workload_name=obo_config["workload_name"],
                provider_name=obo_config["provider_name"],
                scopes=obo_config.get("scopes", ["openid"]),
            )
            if obo_token:
                return obo_token
            logger.warning("OBO exchange failed, falling back to raw JWT")

        # Fallback: pass raw JWT (works but less secure — no scope restriction)
        return user_jwt

    @tool(
        name="fhir_search_patients",
        description=(
            "Search for patients in the FHIR electronic health record system. "
            "Results are automatically filtered to your clinic. "
            "Uses On-Behalf-Of token exchange for secure downstream access. "
            "Use this to find patients by name or list all patients in the EHR."
        ),
    )
    def fhir_search_patients(name: str = None, limit: int = 10) -> str:
        """Search for patients in the FHIR EHR system.

        Args:
            name: Patient name to search for (optional — omit to list all).
            limit: Maximum number of results (default: 10).

        Returns:
            JSON string with matching patients.
        """
        token = _get_fhir_token()
        if not token:
            return "Error: No authentication token available for FHIR access"

        params = {"limit": limit}
        if name:
            params["name"] = name

        result = _call_fhir_api(fhir_api_url, token, "fhir_search_patients", params)

        if "error" in result:
            return f"FHIR Error: {result['error']}"

        patients = result.get("patients", [])
        if not patients:
            return "No patients found in the FHIR system for your clinic."

        formatted = []
        for p in patients:
            formatted.append(
                f"- {p.get('name', 'Unknown')} (ID: {p.get('id')}, "
                f"Gender: {p.get('gender', 'N/A')}, DOB: {p.get('birthDate', 'N/A')})"
            )

        return f"Found {result.get('total', len(patients))} patient(s):\n" + "\n".join(formatted)

    @tool(
        name="fhir_read_patient",
        description=(
            "Read detailed information about a specific patient from the FHIR EHR system. "
            "Requires the patient's FHIR resource ID. "
            "Access is restricted to patients belonging to your clinic."
        ),
    )
    def fhir_read_patient(patient_id: str) -> str:
        """Read a specific patient's full record from FHIR.

        Args:
            patient_id: The FHIR Patient resource ID.

        Returns:
            JSON string with patient details.
        """
        token = _get_fhir_token()
        if not token:
            return "Error: No authentication token available for FHIR access"

        result = _call_fhir_api(fhir_api_url, token, "fhir_read_patient", {"patient_id": patient_id})

        if "error" in result:
            return f"FHIR Error: {result['error']}"

        return json.dumps(result, indent=2)

    @tool(
        name="fhir_search_observations",
        description=(
            "Search for clinical observations (lab results, vitals, measurements) "
            "in the FHIR EHR system. Results are filtered to your clinic. "
            "Can optionally filter by patient or observation category (e.g., 'laboratory', 'vital-signs')."
        ),
    )
    def fhir_search_observations(patient_id: str = None, category: str = None, limit: int = 10) -> str:
        """Search for observations (labs, vitals) in the FHIR system.

        Args:
            patient_id: Filter by specific patient FHIR ID (optional).
            category: Filter by category — 'laboratory' or 'vital-signs' (optional).
            limit: Maximum number of results (default: 10).

        Returns:
            Formatted string with observation results.
        """
        token = _get_fhir_token()
        if not token:
            return "Error: No authentication token available for FHIR access"

        params = {"limit": limit}
        if patient_id:
            params["patient_id"] = patient_id
        if category:
            params["category"] = category

        result = _call_fhir_api(fhir_api_url, token, "fhir_search_observations", params)

        if "error" in result:
            return f"FHIR Error: {result['error']}"

        observations = result.get("observations", [])
        if not observations:
            return "No observations found in the FHIR system for your clinic."

        formatted = []
        for obs in observations:
            formatted.append(
                f"- {obs.get('code', 'Unknown')}: {obs.get('value', 'N/A')} "
                f"(Date: {obs.get('date', 'N/A')}, Status: {obs.get('status', 'N/A')})"
            )

        return f"Found {result.get('total', len(observations))} observation(s):\n" + "\n".join(formatted)

    return [fhir_search_patients, fhir_read_patient, fhir_search_observations]
