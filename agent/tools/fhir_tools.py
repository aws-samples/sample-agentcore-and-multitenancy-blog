# Copyright 2026 Amazon.com and its affiliates; all rights reserved.
# SPDX-License-Identifier: MIT-0

"""
FHIR tool wrappers for the Healthcare Agent.

Uses agent-side token translation to create a scoped, short-lived JWT
for the FHIR resource server. The flow:

  1. Agent has the user's inbound JWT (validated by Runtime's Inbound JWT Authorizer)
  2. Agent decodes the JWT to extract user claims (sub, clinic_id, role)
  3. Agent mints a new short-lived JWT signed with a KMS key, containing:
     - Original user identity (sub)
     - Tenant scope (clinic_id)
     - Agent identity (iss)
     - Target audience (FHIR API)
     - Restricted scopes (fhir:read)
     - Short TTL (60 seconds)
  4. Agent passes the translated token as Bearer to the FHIR API Gateway

This avoids forwarding the raw user JWT end-to-end while maintaining
cryptographic tenant isolation at the FHIR layer.

Demonstrates:
  - Agent-side token translation (no IdP dependency for exchange)
  - Scope restriction without OBO grant type support
  - Tenant isolation via signed claims
  - KMS-based token signing for non-repudiation
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import time
from typing import Optional

import boto3
import requests
from strands import tool

from ..context import TenantContext

logger = logging.getLogger(__name__)

# Cache KMS client
_kms_client = None


def _get_kms_client():
    """Get or create the KMS client for token signing."""
    global _kms_client
    if _kms_client is None:
        region = os.environ.get("AWS_REGION", "us-east-1")
        _kms_client = boto3.client("kms", region_name=region)
    return _kms_client


def _base64url_encode(data: bytes) -> str:
    """Base64url encode without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def _decode_jwt_claims(jwt_token: str) -> Optional[dict]:
    """Decode JWT payload without verification (claims extraction only)."""
    try:
        parts = jwt_token.split(".")
        if len(parts) != 3:
            return None
        payload = parts[1]
        # Add padding
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += "=" * padding
        decoded = base64.urlsafe_b64decode(payload)
        return json.loads(decoded)
    except Exception as e:
        logger.warning(f"Failed to decode JWT claims: {e}")
        return None


def _sign_with_kms(message: bytes, key_id: str) -> Optional[bytes]:
    """Sign a message using KMS HMAC key."""
    try:
        client = _get_kms_client()
        response = client.generate_mac(
            KeyId=key_id,
            Message=message,
            MacAlgorithm="HMAC_SHA_256",
        )
        return response["Mac"]
    except Exception as e:
        logger.error(f"KMS signing failed: {e}")
        return None


def _sign_with_secret(message: bytes, secret: str) -> bytes:
    """Sign a message using HMAC-SHA256 with a shared secret (fallback)."""
    return hmac.HMAC(secret.encode("utf-8"), message, hashlib.sha256).digest()


def _mint_fhir_token(
    user_jwt: str,
    signing_key_id: str = None,
    signing_secret: str = None,
    ttl_seconds: int = 60,
) -> Optional[str]:
    """
    Mint a short-lived, scoped JWT for the FHIR API.

    Extracts user identity from the inbound JWT and creates a new token
    with restricted scope and short TTL, signed by the agent.

    Args:
        user_jwt: The inbound user JWT (from Cognito)
        signing_key_id: KMS key ID for signing (preferred)
        signing_secret: Shared secret for HMAC signing (fallback)
        ttl_seconds: Token lifetime in seconds (default: 60)

    Returns:
        A signed JWT string for the FHIR API, or None on failure.
    """
    # Extract claims from inbound JWT
    claims = _decode_jwt_claims(user_jwt)
    if not claims:
        logger.error("Cannot mint FHIR token: failed to decode inbound JWT")
        return None

    now = int(time.time())

    # Build the translated token payload
    payload = {
        # User identity (from original token)
        "sub": claims.get("sub", "unknown"),
        "email": claims.get("email", ""),
        "username": claims.get("cognito:username", claims.get("username", "")),
        # Tenant context
        "clinic_id": TenantContext.get_clinic_id() or claims.get("custom:clinic_id", "unknown"),
        "tier": TenantContext.get_tier() or "premium",
        "role": TenantContext.get_role() or claims.get("custom:role", "user"),
        # Token metadata
        "iss": "healthcare-agent",
        "aud": "fhir-api",
        "iat": now,
        "exp": now + ttl_seconds,
        # Restricted scopes for FHIR
        "scope": "fhir:read.patients fhir:read.observations",
    }

    # Build JWT
    header = {"alg": "HS256", "typ": "JWT"}
    if signing_key_id:
        header["kid"] = signing_key_id

    header_b64 = _base64url_encode(json.dumps(header, separators=(",", ":")).encode())
    payload_b64 = _base64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")

    # Sign with KMS (preferred) or shared secret (fallback)
    if signing_key_id:
        signature = _sign_with_kms(signing_input, signing_key_id)
        if not signature:
            logger.warning("KMS signing failed, falling back to shared secret")
            if signing_secret:
                signature = _sign_with_secret(signing_input, signing_secret)
            else:
                return None
    elif signing_secret:
        signature = _sign_with_secret(signing_input, signing_secret)
    else:
        logger.error("No signing key or secret configured for token translation")
        return None

    token = f"{header_b64}.{payload_b64}.{_base64url_encode(signature)}"
    logger.info(
        f"Minted FHIR token: sub={payload['sub']}, clinic={payload['clinic_id']}, "
        f"ttl={ttl_seconds}s, scope={payload['scope']}"
    )
    return token


def _call_fhir_api(fhir_api_url: str, token: str, tool_name: str, params: dict) -> dict:
    """
    Call the FHIR API Gateway with Bearer token auth.

    Args:
        fhir_api_url: The FHIR API Gateway endpoint URL
        token: Translated agent-signed token (or fallback user JWT)
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
    Create FHIR tool functions with agent-side token translation.

    Args:
        fhir_api_url: The FHIR API Gateway endpoint URL
        get_token_fn: Callable that returns the current user's JWT
        obo_config: Legacy OBO config (ignored — kept for backward compatibility).
            Token translation config is loaded from SSM/env instead:
            - FHIR_SIGNING_KEY_ID: KMS key ID for token signing
            - FHIR_SIGNING_SECRET: Shared secret fallback (dev/test only)

    Returns:
        List of tool functions to register with the agent
    """
    # Token translation config
    signing_key_id = os.environ.get("FHIR_SIGNING_KEY_ID")
    signing_secret = os.environ.get("FHIR_SIGNING_SECRET")

    if not signing_key_id and not signing_secret:
        # Try SSM as last resort
        try:
            from ..utils import get_ssm_parameter
            signing_key_id = get_ssm_parameter("/app/healthcare/fhir/signing_key_id")
        except Exception:
            # Generate a deterministic secret from the FHIR API URL as dev fallback
            signing_secret = hashlib.sha256(
                f"fhir-token-signing-{fhir_api_url}".encode()
            ).hexdigest()
            logger.warning(
                "No KMS key or signing secret configured for FHIR token translation. "
                "Using derived secret (acceptable for dev, not for production)."
            )

    def _get_fhir_token() -> Optional[str]:
        """Get a translated token for FHIR access."""
        user_jwt = get_token_fn()
        if not user_jwt:
            return None

        # Mint a scoped, short-lived token for the FHIR API
        translated_token = _mint_fhir_token(
            user_jwt=user_jwt,
            signing_key_id=signing_key_id,
            signing_secret=signing_secret,
            ttl_seconds=60,
        )
        if translated_token:
            return translated_token

        # Fallback: pass raw JWT (log warning — should not happen in production)
        logger.warning("Token translation failed, falling back to raw JWT")
        return user_jwt

    @tool(
        name="fhir_search_patients",
        description=(
            "Search for patients in the FHIR electronic health record system. "
            "Results are automatically filtered to your clinic. "
            "Uses scoped token translation for secure downstream access. "
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
