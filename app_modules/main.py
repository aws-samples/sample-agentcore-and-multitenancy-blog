# Copyright 2026 Amazon.com and its affiliates; all rights reserved.
# SPDX-License-Identifier: MIT-0

import streamlit as st
from .auth import AuthManager
from .chat import ChatManager
from .styles import apply_custom_styles
from .ui_components import (
    render_clinic_header,
    render_document_chat_interface,
    render_prompt_suggestions,
    render_document_scope_indicator,
    render_policy_status_banner,
    render_sidebar_user_info,
)


def main():
    """Main application entry point"""
    # Configure page
    st.set_page_config(
        page_title="Healthcare Clinical Assistant",
        page_icon="🏥",
        layout="wide"
    )

    # Apply custom styles
    apply_custom_styles()

    # Initialize managers
    auth_manager = AuthManager()
    chat_manager = ChatManager()

    # Handle OAuth callback
    auth_manager.handle_oauth_callback()

    # Check authentication status
    if auth_manager.is_authenticated():
        # Get user tier and set appropriate agent
        user_claims = auth_manager.get_user_claims()
        if user_claims:
            user_tier = user_claims.get('custom:tenant_id', 'basic')
            chat_manager.set_agent_for_user(user_tier)
        
        # Authenticated user interface
        render_authenticated_interface(auth_manager, chat_manager)
    else:
        # Login interface
        render_login_interface(auth_manager)


def render_authenticated_interface(
    auth_manager: AuthManager, chat_manager: ChatManager
):
    """Render the interface for authenticated users"""
    # Get enhanced user claims with clinic information
    user_claims = auth_manager.get_enhanced_user_claims()
    tokens = auth_manager.get_tokens()
    
    if not user_claims:
        st.error("Unable to retrieve user information. Please log in again.")
        if st.button("Logout"):
            auth_manager.logout()
        return
    
    # Render sidebar with user info and features
    render_sidebar_user_info(user_claims, auth_manager)
    
    # Main content area
    # Clinic header with branding
    render_clinic_header(user_claims)
    
    # Document chat interface description
    render_document_chat_interface()
    
    # Document scope indicator
    render_document_scope_indicator(
        user_claims.get('clinic_id', 'unknown'),
        user_claims.get('tier', 'basic')
    )
    
    # Policy enforcement status (premium tier only)
    render_policy_status_banner(user_claims.get('tier', 'basic'))
    
    # Initialize conversation if needed
    if not st.session_state.get("messages"):
        # Show prompt suggestions before first message
        st.markdown("---")
        suggested_prompt = render_prompt_suggestions(user_claims.get('tier', 'basic'))
        
        if suggested_prompt:
            # User clicked a suggestion
            chat_manager.process_user_message(
                suggested_prompt, 
                auth_manager.get_user_claims(),  # Use original claims for backend
                tokens["id_token"]  # Use ID token for JWT authorization (has 'aud' claim)
            )
            st.rerun()
    else:
        # Display chat history
        chat_manager.display_chat_history()

    # Chat input
    if prompt := st.chat_input("Ask about clinical documents, patient records, or clinic information..."):
        chat_manager.process_user_message(
            prompt, 
            auth_manager.get_user_claims(),  # Use original claims for backend
            tokens["id_token"]  # Use ID token for JWT authorization (has 'aud' claim)
        )


def render_login_interface(auth_manager: AuthManager):
    """Render the login interface"""
    login_url = auth_manager.get_login_url()
    st.markdown(
        f'<meta http-equiv="refresh" content="0;url={login_url}">',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
