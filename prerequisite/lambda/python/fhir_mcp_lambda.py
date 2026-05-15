# Copyright 2026 Amazon.com and its affiliates; all rights reserved.
# SPDX-License-Identifier: MIT-0

"""
FHIR MCP Lambda — Proxies FHIR requests to a public HAPI FHIR server
with JWT-based authentication and tenant-scoped data isolation.

Supports two token types:
  1. Cognito JWT (RS256) — Direct user token, validated against Cognito JWKS
  2. Agent-translated JWT (HS256) — Short-lived, scoped token minted by the agent,
     validated via KMS HMAC key or shared secret

The agent-translated token flow:
  1. Agent receives user's Cognito JWT (validated by Runtime's Inbound JWT Authorizer)
  2. Agent mints a new short-lived JWT with restricted scopes and tenant claims
  3. Agent signs it with a KMS HMAC key
  4. This Lambda validates the signature, checks expiry/audience/scope
  5. Extracts clinic_id from the translated token to scope FHIR queries

The HAPI server is a trusted backend (no auth required on its side).
This Lambda is the auth enforcement boundary — it won't serve data
unless the caller presents a valid token with the correct tenant claims.
"""

import json
import os
import time
import urllib.request
import urllib.error
from typing import Dict, Any, Optional

import jwt
import requests

# --- Configuration ---
FHIR_BASE_URL = os.environ.get("FHIR_BASE_URL", "https://hapi.fhir.org/baseR4")
COGNITO_REGION = os.environ.get("COGNITO_REGION", os.environ.get("AWS_REGION", "us-east-1"))
COGNITO_USER_POOL_ID = os.environ.get("COGNITO_USER_POOL_ID", "")
COGNITO_JWKS_URL = os.environ.get("COGNITO_JWKS_URL", "")

# Agent token translation config
FHIR_SIGNING_KEY_ID = os.environ.get("FHIR_SIGNING_KEY_ID", "")
FHIR_SIGNING_SECRET = os.environ.get("FHIR_SIGNING_SECRET", "")
AGENT_TOKEN_ISSUER = "healthcare-agent"
AGENT_TOKEN_AUDIENCE = "fhir-api"

# Cache JWKS keys (Lambda container reuse)
_jwks_cache = {"keys": None, "fetched_at": 0}
JWKS_CACHE_TTL = 3600  # 1 hour

# Cache KMS client
_kms_client = None


def _get_kms_client():
    """Get or create KMS client for HMAC verification."""
    global _kms_client
    if _kms_client is None:
        import boto3
        _kms_client = boto3.client("kms", region_name=COGNITO_REGION)
    return _kms_client


def _get_jwks_url() -> str:
    """Construct JWKS URL from Cognito configuration."""
    if COGNITO_JWKS_URL:
        return COGNITO_JWKS_URL
    if COGNITO_USER_POOL_ID:
        return (
            f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com/"
            f"{COGNITO_USER_POOL_ID}/.well-known/jwks.json"
        )
    return ""


def _fetch_jwks() -> dict:
    """Fetch and cache JWKS from Cognito."""
    now = time.time()
    if _jwks_cache["keys"] and (now - _jwks_cache["fetched_at"]) < JWKS_CACHE_TTL:
        return _jwks_cache["keys"]

    jwks_url = _get_jwks_url()
    if not jwks_url:
        print("WARNING: No JWKS URL configured, skipping signature verification")
        return None

    try:
        req = urllib.request.Request(jwks_url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            jwks_data = json.loads(resp.read().decode())
            _jwks_cache["keys"] = jwks_data
            _jwks_cache["fetched_at"] = now
            return jwks_data
    except Exception as e:
        print(f"ERROR: Failed to fetch JWKS: {e}")
        return _jwks_cache.get("keys")  # Return stale cache if available


def validate_jwt(token: str) -> Dict[str, Any]:
    """
    Validate JWT and extract claims. Supports two token types:

    1. Agent-translated tokens (HS256, iss=healthcare-agent):
       - Verified via KMS HMAC key or shared secret
       - Checks exp, aud, iss, and required claims (clinic_id, sub)

    2. Cognito tokens (RS256):
       - Verified against Cognito JWKS
       - Falls back to decode-only mode if JWKS unavailable

    Returns:
        Dict with decoded claims.

    Raises:
        ValueError: If token is invalid or expired.
    """
    if not token:
        raise ValueError("No token provided")

    # Peek at the header to determine token type
    try:
        unverified_header = jwt.get_unverified_header(token)
    except Exception as e:
        raise ValueError(f"Malformed token header: {e}")

    alg = unverified_header.get("alg", "")

    # --- Agent-translated token (HS256) ---
    if alg == "HS256":
        return _validate_agent_token(token, unverified_header)

    # --- Cognito token (RS256) ---
    return _validate_cognito_token(token, unverified_header)


def _validate_agent_token(token: str, header: dict) -> Dict[str, Any]:
    """
    Validate an agent-translated HS256 token.

    Verification order:
      1. KMS HMAC key (if FHIR_SIGNING_KEY_ID configured)
      2. Shared secret (if FHIR_SIGNING_SECRET configured)
      3. Reject if neither is configured
    """
    import base64
    import hashlib
    import hmac as hmac_mod

    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid token format")

    signing_input = f"{parts[0]}.{parts[1]}".encode("utf-8")

    # Decode signature
    sig_padded = parts[2] + "=" * (4 - len(parts[2]) % 4) if len(parts[2]) % 4 else parts[2]
    try:
        provided_sig = base64.urlsafe_b64decode(sig_padded)
    except Exception:
        raise ValueError("Invalid token signature encoding")

    # Verify signature
    verified = False

    if FHIR_SIGNING_KEY_ID:
        # Verify with KMS
        try:
            client = _get_kms_client()
            client.verify_mac(
                KeyId=FHIR_SIGNING_KEY_ID,
                Message=signing_input,
                MacAlgorithm="HMAC_SHA_256",
                Mac=provided_sig,
            )
            verified = True
        except client.exceptions.KMSInvalidMacException:
            raise ValueError("Token signature verification failed (KMS)")
        except Exception as e:
            print(f"WARNING: KMS verification error: {e}, trying shared secret fallback")

    if not verified and FHIR_SIGNING_SECRET:
        # Verify with shared secret
        expected_sig = hmac_mod.HMAC(
            FHIR_SIGNING_SECRET.encode("utf-8"), signing_input, hashlib.sha256
        ).digest()
        if not hmac_mod.compare_digest(provided_sig, expected_sig):
            raise ValueError("Token signature verification failed (HMAC)")
        verified = True

    if not verified:
        raise ValueError("No signing key configured to verify agent token")

    # Decode payload
    payload_padded = parts[1] + "=" * (4 - len(parts[1]) % 4) if len(parts[1]) % 4 else parts[1]
    try:
        decoded = json.loads(base64.urlsafe_b64decode(payload_padded))
    except Exception as e:
        raise ValueError(f"Failed to decode token payload: {e}")

    # Validate claims
    now = int(time.time())

    if decoded.get("exp", 0) < now:
        raise ValueError("Agent token has expired")

    if decoded.get("iss") != AGENT_TOKEN_ISSUER:
        raise ValueError(f"Invalid issuer: expected '{AGENT_TOKEN_ISSUER}', got '{decoded.get('iss')}'")

    if decoded.get("aud") != AGENT_TOKEN_AUDIENCE:
        raise ValueError(f"Invalid audience: expected '{AGENT_TOKEN_AUDIENCE}', got '{decoded.get('aud')}'")

    if not decoded.get("sub"):
        raise ValueError("Token missing required 'sub' claim")

    if not decoded.get("clinic_id"):
        raise ValueError("Token missing required 'clinic_id' claim")

    print(f"✅ [fhir_mcp] Agent token validated — sub: {decoded.get('sub')}, scope: {decoded.get('scope', 'N/A')}")
    return decoded


def _validate_cognito_token(token: str, header: dict) -> Dict[str, Any]:
    """Validate a Cognito RS256 token against JWKS."""
    jwks = _fetch_jwks()

    if jwks:
        try:
            kid = header.get("kid")
            rsa_key = None
            for key in jwks.get("keys", []):
                if key.get("kid") == kid:
                    rsa_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key))
                    break

            if not rsa_key:
                raise ValueError(f"Key ID {kid} not found in JWKS")

            decoded = jwt.decode(
                token,
                rsa_key,
                algorithms=["RS256"],
                options={
                    "verify_exp": True,
                    "verify_aud": False,
                },
            )
            return decoded

        except jwt.ExpiredSignatureError:
            raise ValueError("Token has expired")
        except jwt.InvalidTokenError as e:
            raise ValueError(f"Invalid token: {e}")
    else:
        # Fallback: decode without verification (local dev only)
        print("WARNING: Decoding JWT without signature verification (no JWKS configured)")
        try:
            decoded = jwt.decode(token, options={"verify_signature": False})
            return decoded
        except Exception as e:
            raise ValueError(f"Failed to decode token: {e}")


def extract_clinic_id(claims: Dict[str, Any]) -> str:
    """Extract clinic_id from JWT claims (supports both Cognito and agent token formats)."""
    # Agent-translated tokens use top-level 'clinic_id'
    clinic_id = claims.get("clinic_id", "")
    if not clinic_id:
        # Cognito tokens use 'custom:clinic_id'
        clinic_id = claims.get("custom:clinic_id", "demo-clinic")
    return clinic_id


def extract_tier(claims: Dict[str, Any]) -> str:
    """Extract tier from JWT claims (supports both Cognito and agent token formats)."""
    # Agent-translated tokens use top-level 'tier'
    tier = claims.get("tier", "")
    if not tier:
        tier = claims.get("custom:tier", "basic")
    return tier


# --- FHIR Operations ---


def fhir_search_patients(clinic_id: str, name: str = None, limit: int = 10) -> Dict:
    """
    Search for Patient resources scoped to a clinic.

    Uses the Organization tag to filter patients by clinic.
    """
    params = {
        "_count": str(limit),
        "_tag": f"clinic|{clinic_id}",
    }
    if name:
        # HAPI tokenizes name search — use family name for more reliable matching
        # If multiple words, try last word as family name
        name_parts = name.strip().split()
        if len(name_parts) > 1:
            params["family"] = name_parts[-1]
            params["given"] = name_parts[0]
        else:
            params["name"] = name

    try:
        resp = requests.get(
            f"{FHIR_BASE_URL}/Patient",
            params=params,
            headers={"Accept": "application/fhir+json"},
            timeout=15,
        )
        resp.raise_for_status()
        bundle = resp.json()

        # Extract patient summaries
        entries = bundle.get("entry", [])
        patients = []
        for entry in entries:
            resource = entry.get("resource", {})
            name_parts = resource.get("name", [{}])[0]
            patients.append({
                "id": resource.get("id"),
                "name": f"{' '.join(name_parts.get('given', []))} {name_parts.get('family', '')}".strip(),
                "gender": resource.get("gender"),
                "birthDate": resource.get("birthDate"),
            })

        return {
            "total": bundle.get("total", len(patients)),
            "patients": patients,
        }

    except requests.exceptions.RequestException as e:
        return {"error": f"FHIR server request failed: {str(e)}"}


def fhir_read_patient(clinic_id: str, patient_id: str) -> Dict:
    """
    Read a specific Patient resource by ID, with clinic isolation check.
    """
    try:
        resp = requests.get(
            f"{FHIR_BASE_URL}/Patient/{patient_id}",
            headers={"Accept": "application/fhir+json"},
            timeout=15,
        )

        if resp.status_code == 404:
            return {"error": f"Patient {patient_id} not found"}

        resp.raise_for_status()
        patient = resp.json()

        # Verify clinic ownership via tag
        tags = patient.get("meta", {}).get("tag", [])
        patient_clinic = None
        for tag in tags:
            if tag.get("system") == "clinic":
                patient_clinic = tag.get("code")
                break

        if patient_clinic and patient_clinic != clinic_id:
            return {"error": "Access denied — patient belongs to a different clinic"}

        # Format response
        name_parts = patient.get("name", [{}])[0]
        return {
            "id": patient.get("id"),
            "name": f"{' '.join(name_parts.get('given', []))} {name_parts.get('family', '')}".strip(),
            "gender": patient.get("gender"),
            "birthDate": patient.get("birthDate"),
            "address": patient.get("address", []),
            "telecom": patient.get("telecom", []),
            "tags": tags,
        }

    except requests.exceptions.RequestException as e:
        return {"error": f"FHIR server request failed: {str(e)}"}


def fhir_search_observations(clinic_id: str, patient_id: str = None, category: str = None, limit: int = 10) -> Dict:
    """
    Search for Observation resources (lab results, vitals) scoped to a clinic.
    """
    params = {
        "_count": str(limit),
        "_tag": f"clinic|{clinic_id}",
        "_sort": "-date",
    }
    if patient_id:
        params["subject"] = f"Patient/{patient_id}"
    if category:
        params["category"] = category

    try:
        resp = requests.get(
            f"{FHIR_BASE_URL}/Observation",
            params=params,
            headers={"Accept": "application/fhir+json"},
            timeout=15,
        )
        resp.raise_for_status()
        bundle = resp.json()

        entries = bundle.get("entry", [])
        observations = []
        for entry in entries:
            resource = entry.get("resource", {})
            value = resource.get("valueQuantity", {})
            observations.append({
                "id": resource.get("id"),
                "code": resource.get("code", {}).get("text", resource.get("code", {}).get("coding", [{}])[0].get("display", "Unknown")),
                "value": f"{value.get('value', '')} {value.get('unit', '')}".strip() if value else resource.get("valueString", "N/A"),
                "date": resource.get("effectiveDateTime", resource.get("issued", "Unknown")),
                "status": resource.get("status"),
                "subject": resource.get("subject", {}).get("reference", ""),
            })

        return {
            "total": bundle.get("total", len(observations)),
            "observations": observations,
        }

    except requests.exceptions.RequestException as e:
        return {"error": f"FHIR server request failed: {str(e)}"}


# --- Lambda Handler ---


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    FHIR MCP Lambda handler.

    Validates JWT, extracts tenant context, routes to FHIR operations.
    Called via API Gateway with Bearer token authentication.
    """
    try:
        print(f"📋 [fhir_mcp] Received event: {json.dumps(event, indent=2, default=str)}")

        # --- Step 1: Extract and validate JWT ---
        auth_header = event.get("headers", {}).get("Authorization", "")
        if not auth_header:
            # Check lowercase (API Gateway normalizes headers)
            auth_header = event.get("headers", {}).get("authorization", "")

        if not auth_header:
            return _error_response(401, "Missing Authorization header")

        token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else auth_header

        try:
            claims = validate_jwt(token)
            print(f"✅ [fhir_mcp] JWT validated — sub: {claims.get('sub', 'unknown')}")
        except ValueError as e:
            print(f"❌ [fhir_mcp] JWT validation failed: {e}")
            return _error_response(401, f"Authentication failed: {e}")

        # --- Step 2: Extract tenant context from claims ---
        clinic_id = extract_clinic_id(claims)
        tier = extract_tier(claims)
        print(f"🏥 [fhir_mcp] Tenant context — clinic: {clinic_id}, tier: {tier}")

        # --- Step 3: Parse request body and route to FHIR operation ---
        body = event.get("body", "{}")
        if isinstance(body, str):
            body = json.loads(body) if body else {}

        tool_name = body.get("tool", "")
        params = body.get("params", {})

        print(f"🔧 [fhir_mcp] Tool: {tool_name}, Params: {json.dumps(params)}")

        # Route to appropriate FHIR operation
        if tool_name == "fhir_search_patients":
            result = fhir_search_patients(
                clinic_id=clinic_id,
                name=params.get("name"),
                limit=params.get("limit", 10),
            )

        elif tool_name == "fhir_read_patient":
            patient_id = params.get("patient_id")
            if not patient_id:
                return _error_response(400, "patient_id is required")
            result = fhir_read_patient(clinic_id=clinic_id, patient_id=patient_id)

        elif tool_name == "fhir_search_observations":
            result = fhir_search_observations(
                clinic_id=clinic_id,
                patient_id=params.get("patient_id"),
                category=params.get("category"),
                limit=params.get("limit", 10),
            )

        else:
            return _error_response(400, f"Unknown tool: {tool_name}. Available: fhir_search_patients, fhir_read_patient, fhir_search_observations")

        # --- Step 4: Return result ---
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "X-Clinic-ID": clinic_id,
                "X-Tier": tier,
            },
            "body": json.dumps(result, default=str),
        }

    except Exception as e:
        print(f"❌ [fhir_mcp] Unhandled error: {e}")
        import traceback
        traceback.print_exc()
        return _error_response(500, f"Internal server error: {str(e)}")


def _error_response(status_code: int, message: str) -> Dict:
    """Build a standard error response."""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps({"error": message}),
    }
