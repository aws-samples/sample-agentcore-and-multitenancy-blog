import json
import re
import time
import uuid
import urllib.parse
from typing import Any, Optional
import requests
import streamlit as st
from scripts.utils import read_config, get_aws_region
from .utils import make_urls_clickable, create_safe_markdown_text


def remove_thinking_tags(text):
    """Remove <thinking>...</thinking> content from the response"""
    # Remove thinking tags and their content using regex
    cleaned_text = re.sub(r'<thinking>.*?</thinking>', '', text, flags=re.DOTALL | re.IGNORECASE)
    # Clean up any extra whitespace
    cleaned_text = re.sub(r'\n\s*\n', '\n\n', cleaned_text.strip())
    return cleaned_text


class ChatManager:
    def __init__(self, api_gateway_url: str = None):
        self.auth_url_matching = ".amazonaws.com/identities/oauth2/authorize"
        self.api_gateway_url = api_gateway_url or self._get_api_gateway_url()
        self._init_session_state()

    def _get_api_gateway_url(self) -> str:
        """Get API Gateway URL from environment or config"""
        return "https://xtyyaiwkib.execute-api.us-east-1.amazonaws.com/prod"

    def _init_session_state(self):
        """Initialize session state variables"""
        if "session_id" not in st.session_state:
            st.session_state["session_id"] = str(uuid.uuid4())

        # Agent ARN will be set dynamically based on user tier
        # Don't initialize it here anymore

        if "region" not in st.session_state:
            st.session_state["region"] = get_aws_region()

        if "messages" not in st.session_state:
            st.session_state["messages"] = []

        if "pending_assistant" not in st.session_state:
            st.session_state["pending_assistant"] = False
    
    def set_agent_for_user(self, user_tier: str):
        """Set the agent ARN based on user tier"""
        runtime_config = read_config(".bedrock_agentcore.yaml")
        
        # Map tier to agent name
        tier_to_agent = {
            "basic": "healthcare_basic",
            "premium": "healthcare_premium"
        }
        
        agent_name = tier_to_agent.get(user_tier, "healthcare_basic")
        
        # Set agent ARN in session state
        st.session_state["agent_arn"] = runtime_config["agents"][agent_name]["bedrock_agentcore"]["agent_arn"]
        st.session_state["agent_name"] = agent_name

    def invoke_endpoint(
        self,
        agent_arn: str,
        payload,
        session_id: str,
        bearer_token: Optional[str],
        tenant_id: str = "default",
        endpoint_name: str = "DEFAULT",
    ) -> Any:
        """Invoke agent endpoint via API Gateway with tenant ID."""
        escaped_arn = urllib.parse.quote(agent_arn, safe="")
        url = f"{self.api_gateway_url}/runtimes/{escaped_arn}/invocations"

        # Map tenant to API key for throttling
        api_key_mapping = {
            "premium": "XhdzLgEC1Q5p1rfN5ETe91BcWwizCURo1InwaDbw",  # Premium API key value
            "basic": "Vanb9c26QF1Ixz5mZJiEC4ZBWaNitZlsatM5p6DR",   # Basic API key value
            "default": "Vanb9c26QF1Ixz5mZJiEC4ZBWaNitZlsatM5p6DR"  # Default to basic
        }
        
        api_key = api_key_mapping.get(tenant_id, "swqp2a46ph")

        headers = {
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
            "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": session_id,
            "X-Tenant-ID": tenant_id,
            "X-API-Key": api_key,  # Add API key for throttling
        }

        try:
            body = json.loads(payload) if isinstance(payload, str) else payload
        except json.JSONDecodeError:
            body = {"payload": payload}

        try:
            print(f"DEBUG: Making request to URL: {url}")
            print(f"DEBUG: Headers: {headers}")
            print(f"DEBUG: Body: {json.dumps(body)}")
            
            response = requests.post(
                url,
                params={"qualifier": endpoint_name},
                headers=headers,
                json=body,
                timeout=100,
                stream=True,
            )
            
            print(f"DEBUG: Response status code: {response.status_code}")
            print(f"DEBUG: Response headers: {dict(response.headers)}")
            
            if response.status_code != 200:
                if response.status_code == 429:
                    yield "⚠️ You have exceeded your weekly quota. Please wait for the quota to reset or contact your account manager to explore options if you would like to use the service now."
                elif response.status_code == 403:
                    yield "🔒 Access denied. Please check your permissions or contact support."
                elif response.status_code == 500:
                    yield "🛠️ We're experiencing technical difficulties. Please try again in a few moments."
                elif response.status_code == 504:
                    yield "⏱️ The request is taking longer than expected. Please try again with a shorter message."
                else:
                    yield f"❌ Service temporarily unavailable (Error {response.status_code}). Please try again later."
                return
                
            # Debug: Print first chunk of response
            response_content = response.text
            print(f"DEBUG: Response content: {response_content[:200]}...")
            
            # Handle streaming response
            if response_content:
                yield response_content
                return
                
            last_data = False
            for line in response.iter_lines(chunk_size=1):
                if line:
                    line = line.decode("utf-8")
                    if line.startswith("data: "):
                        last_data = True
                        line = line[6:]
                        line = line.replace('"', "")
                        yield line
                    elif line:
                        line = line.replace('"', "")
                        if last_data:
                            yield "\n" + line
                        last_data = False

        except requests.exceptions.RequestException as e:
            print("Failed to invoke agent endpoint via API Gateway: %s", str(e))
            raise

    def _get_tenant_id(self, user_claims: dict) -> str:
        """Extract tenant ID from user claims"""
        return user_claims.get('custom:tenant_id', 'default')

    def display_chat_history(self):
        """Display chat messages from history"""
        messages_to_show = st.session_state.messages[:]

        if (
            st.session_state.get("pending_assistant", False)
            and messages_to_show
            and messages_to_show[-1]["role"] == "user"
        ):
            messages_to_show = messages_to_show[:-1]

        for message in messages_to_show:
            bubble_class = (
                "user-bubble" if message["role"] == "user" else "assistant-bubble"
            )
            emoji = "🧑‍💻" if message["role"] == "user" else "🤖"

            with st.chat_message(message["role"]):
                if message["role"] == "assistant" and "elapsed" in message:
                    clickable_content = make_urls_clickable(message["content"])
                    create_safe_markdown_text(
                        f'<div class="{bubble_class}">{emoji} {clickable_content}<br><span style="font-size:0.9em;color:#888;">⏱️ Response time: {message["elapsed"]:.2f} seconds</span></div>',
                        st,
                    )
                else:
                    if message["role"] == "assistant":
                        clickable_content = make_urls_clickable(message["content"])
                        create_safe_markdown_text(
                            f'<div class="{bubble_class}">{emoji} {clickable_content}</div>',
                            st,
                        )
                    else:
                        create_safe_markdown_text(
                            f'<span class="{bubble_class}">{emoji} {message["content"]}</span>',
                            st,
                        )

    def process_user_message(self, prompt: str, user_claims: dict, bearer_token: str):
        """Process a user message and get assistant response"""
        st.session_state.messages.append({"role": "user", "content": prompt})
        tenant_id = self._get_tenant_id(user_claims)

        with st.chat_message("user"):
            create_safe_markdown_text(
                f'<span class="user-bubble">🧑‍💻 {prompt}</span>', st
            )
            st.session_state["pending_assistant"] = True

        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            start_time = time.time()

            create_safe_markdown_text(
                '<span class="thinking-bubble">🤖 💭 Customer Support Assistant is thinking...</span>',
                message_placeholder,
            )

            chunk_count = 0
            accumulated_response = ""

            for chunk in self.invoke_endpoint(
                agent_arn=st.session_state["agent_arn"],
                payload=json.dumps(
                    {"prompt": prompt, "actor_id": user_claims.get("cognito:username")}
                ),
                bearer_token=bearer_token,
                session_id=st.session_state["session_id"],
                tenant_id=tenant_id,
            ):
                chunk = str(chunk)
                if chunk.strip():
                    if self.auth_url_matching in chunk:
                        accumulated_response = f"Please use {chunk}"
                    else:
                        accumulated_response += chunk
                    chunk_count += 1

                    if chunk_count % 3 == 0:
                        accumulated_response += ""

                    clickable_streaming_text = make_urls_clickable(remove_thinking_tags(accumulated_response))

                    create_safe_markdown_text(
                        f'<div class="assistant-bubble streaming typing-cursor">🤖 {clickable_streaming_text}</div>',
                        message_placeholder,
                    )

                    if self.auth_url_matching in accumulated_response:
                        accumulated_response = str()

                    time.sleep(0.02)

            elapsed = time.time() - start_time
            clickable_streaming_text = make_urls_clickable(remove_thinking_tags(accumulated_response))

            create_safe_markdown_text(
                f'<div class="assistant-bubble">🤖 {clickable_streaming_text}<br><span style="font-size:0.9em;color:#888;">⏱️ Response time: {elapsed:.2f} seconds</span></div>',
                message_placeholder,
            )

            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": remove_thinking_tags(accumulated_response),
                    "elapsed": elapsed,
                }
            )
            st.session_state["pending_assistant"] = False

    def initialize_default_conversation(self, user_claims: dict, bearer_token: str):
        """Initialize the conversation with a default message"""
        if not st.session_state.messages:
            default_prompt = f"Hi my email is {user_claims.get('email')}"
            tenant_id = self._get_tenant_id(user_claims)
            st.session_state.messages = [{"role": "user", "content": default_prompt}]

            with st.chat_message("user"):
                create_safe_markdown_text(
                    f'<span class="user-bubble">🧑‍💻 {default_prompt}</span>', st
                )
                st.session_state["pending_assistant"] = True

            with st.chat_message("assistant"):
                message_placeholder = st.empty()
                start_time = time.time()

                create_safe_markdown_text(
                    '<span class="thinking-bubble">🤖 💭 Customer Support Assistant is thinking...</span>',
                    message_placeholder,
                )

                chunk_count = 0
                accumulated_response = ""

                for chunk in self.invoke_endpoint(
                    agent_arn=st.session_state["agent_arn"],
                    payload=json.dumps(
                        {
                            "prompt": default_prompt,
                            "actor_id": user_claims.get("cognito:username"),
                        }
                    ),
                    bearer_token=bearer_token,
                    session_id=st.session_state["session_id"],
                    tenant_id=tenant_id,
                ):
                    chunk = str(chunk)
                    if chunk.strip():
                        accumulated_response += chunk
                        chunk_count += 1

                        if chunk_count % 3 == 0:
                            accumulated_response += ""

                        clickable_streaming_text = make_urls_clickable(
                            accumulated_response
                        )

                        create_safe_markdown_text(
                            f'<div class="assistant-bubble streaming typing-cursor">🤖 {clickable_streaming_text}</div>',
                            message_placeholder,
                        )

                        time.sleep(0.02)

                elapsed = time.time() - start_time
                clickable_answer = make_urls_clickable(accumulated_response)

                create_safe_markdown_text(
                    f'<div class="assistant-bubble">🤖 {clickable_answer}<br><span style="font-size:0.9em;color:#888;">⏱️ Response time: {elapsed:.2f} seconds</span></div>',
                    message_placeholder,
                )

                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": accumulated_response,
                        "elapsed": elapsed,
                    }
                )
                st.session_state["pending_assistant"] = False
                st.rerun()
