"""
Healthcare-specific UI components for the Streamlit application.
"""

import streamlit as st
from typing import Dict, Any


def render_clinic_header(user_claims: Dict[str, Any]):
    """
    Display clinic branding and user information in the header.
    
    Args:
        user_claims: Enhanced user claims with clinic information
    """
    tier = user_claims.get('tier', 'basic')
    clinic_name = user_claims.get('clinic_name', 'Healthcare Clinic')
    role = user_claims.get('role', 'user').title()
    
    # Tier-specific styling
    tier_badge_color = "#4CAF50" if tier == "premium" else "#2196F3"
    tier_label = "Premium" if tier == "premium" else "Basic"
    
    st.markdown(
        f"""
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                    padding: 20px; border-radius: 10px; margin-bottom: 20px;">
            <h2 style="color: white; margin: 0;">🏥 {clinic_name}</h2>
            <div style="display: flex; gap: 10px; margin-top: 10px;">
                <span style="background-color: {tier_badge_color}; color: white; 
                             padding: 5px 15px; border-radius: 15px; font-size: 0.9em;">
                    {tier_label} Tier
                </span>
                <span style="background-color: rgba(255,255,255,0.2); color: white; 
                             padding: 5px 15px; border-radius: 15px; font-size: 0.9em;">
                    {role}
                </span>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )


def render_document_chat_interface():
    """
    Render the document-focused chat interface with healthcare context.
    """
    st.markdown(
        """
        <div style="background: linear-gradient(135deg, #1e3a5f 0%, #0f2744 100%); 
                    padding: 15px; border-radius: 8px; 
                    border-left: 4px solid #3182ce; margin-bottom: 20px;
                    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);">
            <h4 style="margin: 0 0 10px 0; color: #90cdf4;">📄 Clinical Document Assistant</h4>
            <p style="margin: 0; color: #cbd5e0; font-size: 0.95em;">
                Ask questions about patient records, lab results, appointment notes, and other clinical documents 
                within your clinic's scope. All queries are isolated to your clinic's data.
            </p>
        </div>
        """,
        unsafe_allow_html=True
    )


def render_clinical_results(content: str, elapsed: float = None):
    """
    Display clinical results with structured formatting.
    
    Args:
        content: The response content to display
        elapsed: Optional response time in seconds
    """
    # Add clinical context styling
    st.markdown(
        f"""
        <div class="clinical-result">
            {content}
        </div>
        """,
        unsafe_allow_html=True
    )
    
    if elapsed:
        st.caption(f"⏱️ Response time: {elapsed:.2f} seconds")


def render_tier_features_sidebar(tier: str):
    """
    Display tier-specific features in the sidebar.
    
    Args:
        tier: User's tier (basic or premium)
    """
    st.sidebar.markdown("### 🎯 Your Features")
    
    if tier == "premium":
        st.sidebar.markdown(
            """
            ✅ **Premium Features:**
            - Advanced document analysis
            - Multi-document correlation
            - Web search for clinical guidelines
            - Higher rate limits (2 req/sec)
            - Extended daily quota (20 requests)
            - Priority support
            """
        )
    else:
        st.sidebar.markdown(
            """
            ✅ **Basic Features:**
            - Document search & retrieval
            - Basic summarization
            - Patient context lookup
            - Clinic configuration access
            
            💡 **Upgrade to Premium for:**
            - Web search capabilities
            - Advanced analytics
            - Higher rate limits
            """
        )


def render_prompt_suggestions(tier: str):
    """
    Display prompt suggestions for clinical assistant.
    All tiers share the same suggestions; the last one is marked as premium-only.
    
    Args:
        tier: User's tier (basic or premium)
    """
    st.markdown("### 💡 Suggested Queries")
    
    suggestions = [
        "List all patients in my clinic",
        "Get me patient P50001 info",
        "Get me documents that I have access to",
        "Get me the latest COVID-19 guidance ⭐ Premium",
    ]
    
    cols = st.columns(2)
    for idx, suggestion in enumerate(suggestions):
        with cols[idx % 2]:
            if st.button(suggestion, key=f"suggestion_{idx}", use_container_width=True):
                # Strip the premium badge before sending as prompt
                clean_prompt = suggestion.replace(" ⭐ Premium", "")
                return clean_prompt
    
    return None


def render_document_scope_indicator(clinic_id: str, tier: str):
    """
    Display document scope indicator to show data isolation.
    
    Args:
        clinic_id: The clinic identifier
        tier: User's tier (basic or premium)
    """
    st.markdown(
        f"""
        <div style="background: linear-gradient(135deg, #2d3748 0%, #1a202c 100%); 
                    padding: 10px; border-radius: 5px; 
                    border-left: 3px solid #f6ad55; margin-bottom: 15px;
                    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);">
            <small style="color: #e2e8f0;">
                🔒 <strong>Document Scope:</strong> {clinic_id} ({tier} tier)
                <br>
                <em style="color: #cbd5e0;">You can only access documents within your clinic's scope.</em>
            </small>
        </div>
        """,
        unsafe_allow_html=True
    )

def render_policy_status_banner(tier: str):
    """
    Display policy enforcement status for users.
    Shows business hours restriction on patient data access.

    Args:
        tier: User's tier (basic or premium)
    """

    from datetime import datetime, timezone, timedelta

    # Use US Eastern with proper DST handling
    from zoneinfo import ZoneInfo
    eastern = ZoneInfo("America/New_York")
    now = datetime.now(eastern)
    current_hour = now.hour
    is_business_hours = 8 <= current_hour < 18
    time_str = now.strftime("%-I:%M %p ET")

    if is_business_hours:
        # Calculate minutes until 6pm
        closing = now.replace(hour=18, minute=0, second=0, microsecond=0)
        remaining = closing - now
        hours_left, remainder = divmod(int(remaining.total_seconds()), 3600)
        mins_left = remainder // 60
        remaining_str = f"{hours_left}h {mins_left}m" if hours_left else f"{mins_left}m"

        st.markdown(
            f"""
            <div style="background: linear-gradient(135deg, #1a3a2a 0%, #0f2a1a 100%);
                        padding: 10px 15px; border-radius: 5px;
                        border-left: 3px solid #48bb78; margin-bottom: 15px;
                        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);">
                <small style="color: #c6f6d5;">
                    🛡️ <strong>Policy Status:</strong> Patient data access
                    <strong style="color: #68d391;">ACTIVE</strong>
                    &nbsp;·&nbsp; {time_str} &nbsp;·&nbsp; {remaining_str} remaining until 6:00 PM
                    <br>
                    <em style="color: #9ae6b4;">Business hours policy: patient records available 8:00 AM – 6:00 PM</em>
                </small>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        if current_hour < 8:
            next_open = "8:00 AM today"
        else:
            next_open = "8:00 AM tomorrow"

        st.markdown(
            f"""
            <div style="background: linear-gradient(135deg, #3a1a1a 0%, #2a0f0f 100%);
                        padding: 10px 15px; border-radius: 5px;
                        border-left: 3px solid #fc8181; margin-bottom: 15px;
                        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);">
                <small style="color: #fed7d7;">
                    🛡️ <strong>Policy Status:</strong> Patient data access
                    <strong style="color: #fc8181;">RESTRICTED</strong>
                    &nbsp;·&nbsp; {time_str} &nbsp;·&nbsp; Resumes {next_open}
                    <br>
                    <em style="color: #feb2b2;">Business hours policy: patient records are only available 8:00 AM – 6:00 PM.
                    Document search and clinic configuration remain available.</em>
                </small>
            </div>
            """,
            unsafe_allow_html=True,
        )



def render_sidebar_user_info(user_claims: Dict[str, Any], auth_manager):
    """
    Render user information and controls in the sidebar.
    
    Args:
        user_claims: Enhanced user claims
        auth_manager: Authentication manager instance
    """
    st.sidebar.title("👤 User Information")
    
    st.sidebar.markdown(f"**Email:** {user_claims.get('email', 'N/A')}")
    st.sidebar.markdown(f"**Clinic:** {user_claims.get('clinic_name', 'N/A')}")
    st.sidebar.markdown(f"**Role:** {user_claims.get('role', 'user').title()}")
    st.sidebar.markdown(f"**Tier:** {user_claims.get('tier', 'basic').title()}")
    
    st.sidebar.markdown("---")
    
    # Tier features
    render_tier_features_sidebar(user_claims.get('tier', 'basic'))
    
    # Policy status in sidebar (premium only)
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🛡️ Access Policies")
    
    from datetime import datetime
    from zoneinfo import ZoneInfo
    eastern = ZoneInfo("America/New_York")
    current_hour = datetime.now(eastern).hour
    is_business_hours = 8 <= current_hour < 18
    
    if is_business_hours:
        st.sidebar.markdown("🟢 Patient data: **Available**")
    else:
        st.sidebar.markdown("🔴 Patient data: **Restricted**")
        st.sidebar.caption("Business hours: 8 AM – 6 PM ET")
    st.sidebar.markdown("🟢 Clinic config: **Available**")
    st.sidebar.markdown("🟢 Document search: **Available**")
    
    st.sidebar.markdown("---")
    
    # Session information (collapsible)
    with st.sidebar.expander("🔧 Session Details"):
        st.code(st.session_state.get("session_id", "N/A"), language=None)
        st.caption("Agent ARN")
        st.code(st.session_state.get("agent_arn", "N/A"), language=None)
    
    # Logout button
    if st.sidebar.button("🚪 Logout", use_container_width=True):
        auth_manager.logout()
