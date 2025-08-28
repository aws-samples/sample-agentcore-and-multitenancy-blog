import sys
import os
import streamlit as st

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app_modules.auth import AuthManager
from app_modules.chat_with_api_gateway import ChatManager
from app_modules.styles import apply_custom_styles


def main():
    """Main application entry point with API Gateway routing"""
    # Parse command line arguments
    agent_name = "customersupport"  # Changed default
    if len(sys.argv) > 1:
        for arg in sys.argv:
            if arg.startswith("--agent="):
                agent_name = arg.split("=")[1]

    # Configure page
    st.set_page_config(layout="wide")

    # Apply custom styles
    apply_custom_styles()

    # Initialize managers with API Gateway URL
    auth_manager = AuthManager()
    api_gateway_url = os.environ.get('API_GATEWAY_URL')
    chat_manager = ChatManager(agent_name, api_gateway_url)

    # Handle OAuth callback
    auth_manager.handle_oauth_callback()

    # Check authentication status
    if auth_manager.is_authenticated():
        # Authenticated user interface
        render_authenticated_interface(auth_manager, chat_manager)
    else:
        # Login interface
        render_login_interface(auth_manager)


def render_authenticated_interface(
    auth_manager: AuthManager, chat_manager: ChatManager
):
    """Render the interface for authenticated users"""
    # Sidebar
    st.sidebar.title("Access Tokens")
    st.sidebar.code(auth_manager.cookies.get("tokens"))

    if st.sidebar.button("Logout"):
        auth_manager.logout()

    st.sidebar.write("Agent Arn")
    st.sidebar.code(st.session_state["agent_arn"])

    st.sidebar.write("Session Id")
    st.sidebar.code(st.session_state["session_id"])
    
    # Show API Gateway URL
    st.sidebar.write("API Gateway URL")
    st.sidebar.code(chat_manager.api_gateway_url)

    # Main content
    st.title("Customer Support Assistant (via API Gateway)")
    st.markdown(
        """
        <hr style='border:1px solid #298dff;'>
        """,
        unsafe_allow_html=True,
    )

    # Get user info and tokens
    tokens = auth_manager.get_tokens()
    user_claims = auth_manager.get_user_claims()
    
    # Show tenant info
    tenant_id = user_claims.get('custom:tenant_id', 'default')
    st.info(f"Tenant ID: {tenant_id}")

    # Initialize conversation if needed
    if not st.session_state.get("messages"):
        chat_manager.initialize_default_conversation(
            user_claims, tokens["access_token"]
        )
    else:
        # Display chat history
        chat_manager.display_chat_history()

    # Chat input
    if prompt := st.chat_input("Ask customer support assistant questions!"):
        chat_manager.process_user_message(prompt, user_claims, tokens["access_token"])


def render_login_interface(auth_manager: AuthManager):
    """Render the login interface"""
    login_url = auth_manager.get_login_url()
    st.markdown(
        f'<meta http-equiv="refresh" content="0;url={login_url}">',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
