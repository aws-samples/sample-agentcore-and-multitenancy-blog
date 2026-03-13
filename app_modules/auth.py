import base64
import hashlib
import os
import uuid
import json
import jwt
from jwt import PyJWKClient
from urllib.parse import urlencode
import requests
import streamlit as st
from streamlit_cookies_controller import CookieController
from scripts.utils import get_ssm_parameter


class AuthManager:
    def __init__(self):
        self.cognito_domain = get_ssm_parameter(
            "/app/healthcare/agentcore/cognito_domain"
        ).replace("https://", "")
        self.client_id = get_ssm_parameter(
            "/app/healthcare/agentcore/web_client_id"
        )
        self.user_pool_id = get_ssm_parameter(
            "/app/healthcare/agentcore/userpool_id"
        )
        self.region = self.user_pool_id.split("_")[0] if "_" in self.user_pool_id else "us-east-1"
        self.jwks_url = f"https://cognito-idp.{self.region}.amazonaws.com/{self.user_pool_id}/.well-known/jwks.json"
        self._jwks_client = PyJWKClient(self.jwks_url, cache_keys=True)
        self.redirect_uri = "http://localhost:8501/"
        self.scopes = "email openid profile"
        self.cookies = CookieController()

    def generate_pkce_pair(self):
        code_verifier = (
            base64.urlsafe_b64encode(os.urandom(40)).decode("utf-8").rstrip("=")
        )
        code_challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
            .decode("utf-8")
            .rstrip("=")
        )
        return code_verifier, code_challenge

    def logout(self):
        self.cookies.remove("tokens")

        # Clear session state
        if "session_id" in st.session_state:
            del st.session_state["session_id"]
        if "messages" in st.session_state:
            del st.session_state["messages"]
        if "agent_arn" in st.session_state:
            del st.session_state["agent_arn"]
        if "pending_assistant" in st.session_state:
            del st.session_state["pending_assistant"]
        if "region" in st.session_state:
            del st.session_state["region"]

        logout_url = f"https://{self.cognito_domain}/logout?" + urlencode(
            {"client_id": self.client_id, "logout_uri": self.redirect_uri}
        )

        st.markdown(
            f'<meta http-equiv="refresh" content="0;url={logout_url}">',
            unsafe_allow_html=True,
        )
        st.rerun()

    def handle_oauth_callback(self):
        query_params = st.query_params
        if (
            query_params.get("code")
            and query_params.get("state")
            and not self.cookies.get("tokens")
        ):
            auth_code = query_params.get("code")
            returned_state = query_params.get("state")

            code_verifier = self.cookies.get("code_verifier")
            state = self.cookies.get("oauth_state")

            if not state:
                st.stop()

            if returned_state != state:
                st.error("State mismatch - potential CSRF detected")
                st.stop()

            # Exchange authorization code for tokens
            token_url = f"https://{self.cognito_domain}/oauth2/token"
            data = {
                "grant_type": "authorization_code",
                "client_id": self.client_id,
                "code": auth_code,
                "redirect_uri": self.redirect_uri,
                "code_verifier": code_verifier,
            }
            headers = {"Content-Type": "application/x-www-form-urlencoded"}
            response = requests.post(token_url, data=data, headers=headers, timeout=30)

            if response.ok:
                tokens = response.json()
                self.cookies.set("tokens", json.dumps(tokens))
                self.cookies.remove("code_verifier")
                self.cookies.remove("code_challenge")
                self.cookies.remove("oauth_state")
                st.query_params.clear()
            else:
                st.error(
                    f"Failed to exchange token: {response.status_code} - {response.text}"
                )

    def get_login_url(self):
        code_verifier, code_challenge = self.generate_pkce_pair()
        self.cookies.set("code_verifier", code_verifier)
        self.cookies.set("code_challenge", code_challenge)
        state = str(uuid.uuid4())
        self.cookies.set("oauth_state", state)

        login_params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": self.scopes,
            "code_challenge_method": "S256",
            "code_challenge": self.cookies.get("code_challenge"),
            "state": self.cookies.get("oauth_state"),
        }
        return (
            f"https://{self.cognito_domain}/oauth2/authorize?{urlencode(login_params)}"
        )

    def is_authenticated(self):
        return bool(self.cookies.get("tokens"))

    def get_tokens(self):
        tokens_data = self.cookies.get("tokens")
        if not tokens_data:
            return None

        # Handle both string and dict cases
        if isinstance(tokens_data, str):
            return json.loads(tokens_data)
        elif isinstance(tokens_data, dict):
            return tokens_data
        else:
            return None

    def get_user_claims(self):
        tokens = self.get_tokens()
        if tokens:
            try:
                signing_key = self._jwks_client.get_signing_key_from_jwt(tokens["id_token"])
                return jwt.decode(
                    tokens["id_token"],
                    signing_key.key,
                    algorithms=["RS256"],
                    audience=self.client_id,
                    issuer=f"https://cognito-idp.{self.region}.amazonaws.com/{self.user_pool_id}",
                )
            except jwt.exceptions.PyJWTError:
                return None
        return None

    def get_enhanced_user_claims(self):
        """Extract enhanced user claims including clinic information for healthcare context."""
        claims = self.get_user_claims()
        if not claims:
            return None
        
        # Extract healthcare-specific attributes
        enhanced_claims = {
            'email': claims.get('email', 'Unknown'),
            'username': claims.get('cognito:username', 'Unknown'),
            'tier': claims.get('custom:tenant_id', 'basic'),
            'clinic_id': claims.get('custom:clinic_id', 'unknown-clinic'),
            'role': claims.get('custom:role', 'user'),
        }
        
        # Add display-friendly clinic name
        clinic_names = {
            'clinic-a': 'Family Practice Medical Center',
            'clinic-b': 'QuickCare Urgent Care',
            'clinic-c': 'Bright Beginnings Pediatrics',
            'clinic-d': 'Wellness Internal Medicine',
            'hospital-a': 'Metropolitan Multi-Specialty Medical Center',
            'clinic-e': 'Advanced Cardiology Associates',
            'clinic-f': 'Comprehensive Cancer Care Center',
            'hospital-b': 'University Academic Medical Center',
        }
        enhanced_claims['clinic_name'] = clinic_names.get(
            enhanced_claims['clinic_id'], 
            enhanced_claims['clinic_id'].replace('-', ' ').title()
        )
        
        return enhanced_claims
