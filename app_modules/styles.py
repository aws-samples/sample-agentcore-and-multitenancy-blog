import streamlit as st


def apply_custom_styles():
    """Apply custom CSS styles to the Streamlit app"""
    st.markdown(
        """
        <style>
        /* Main app background */
        body {
            background: #0f1419 !important;
        }
        .stApp {
            background: #0f1419 !important;
        }
        
        /* Chat input styling */
        .stChatInput {
            background: #1a1f2e !important;
            border: 1px solid #2d3748 !important;
            border-radius: 12px !important;
        }
        .stChatInput input {
            background: #1a1f2e !important;
            color: #e2e8f0 !important;
            border: none !important;
        }
        .stChatInput input::placeholder {
            color: #718096 !important;
        }
        
        /* Button styling */
        .stButton button {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
            color: white !important;
            border: none !important;
            border-radius: 8px !important;
            padding: 0.5rem 1rem !important;
            font-weight: 500 !important;
            transition: all 0.3s ease !important;
        }
        .stButton button:hover {
            transform: translateY(-2px) !important;
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4) !important;
        }
        
        /* Chat bubbles */
        .user-bubble {
            background: linear-gradient(135deg, #2d3748 0%, #1a202c 100%);
            color: #e2e8f0;
            border-radius: 16px;
            padding: 0.8rem 1.2rem;
            margin-bottom: 0.5rem;
            display: inline-block;
            border: 1px solid #4a5568;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
        }
        .assistant-bubble {
            background: linear-gradient(135deg, #1e3a5f 0%, #0f2744 100%);
            color: #e2e8f0;
            border-radius: 16px;
            padding: 0.8rem 1.2rem;
            margin-bottom: 0.5rem;
            display: block;
            border: 1px solid #3182ce;
            animation: fadeInUp 0.3s ease-out;
            white-space: pre-wrap;
            word-wrap: break-word;
            max-width: 100%;
            box-shadow: 0 2px 12px rgba(49, 130, 206, 0.2);
        }
        .assistant-bubble.streaming {
            border: 1px solid #4299e1;
            box-shadow: 0 0 20px rgba(66, 153, 225, 0.4);
            animation: pulse-border 2s infinite, fadeInUp 0.3s ease-out;
        }
        .thinking-bubble {
            background: linear-gradient(135deg, #1e3a5f 0%, #0f2744 100%);
            color: #90cdf4;
            border-radius: 16px;
            padding: 0.8rem 1.2rem;
            margin-bottom: 0.5rem;
            display: inline-block;
            border: 1px solid #3182ce;
            animation: thinking-pulse 1.5s infinite, fadeInUp 0.3s ease-out;
            box-shadow: 0 2px 12px rgba(49, 130, 206, 0.2);
        }
        .typing-cursor::after {
            content: '▋';
            color: #63b3ed;
            animation: cursor-blink 1s infinite;
            margin-left: 2px;
        }
        
        /* Animations */
        @keyframes fadeInUp {
            from {
                opacity: 0;
                transform: translateY(20px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        @keyframes pulse-border {
            0%, 100% {
                border-color: #3182ce;
                box-shadow: 0 0 10px rgba(49, 130, 206, 0.3);
            }
            50% {
                border-color: #4299e1;
                box-shadow: 0 0 20px rgba(66, 153, 225, 0.6);
            }
        }
        @keyframes thinking-pulse {
            0%, 100% {
                opacity: 1;
                transform: scale(1);
            }
            50% {
                opacity: 0.85;
                transform: scale(1.01);
            }
        }
        @keyframes cursor-blink {
            0%, 50% {
                opacity: 1;
            }
            51%, 100% {
                opacity: 0;
            }
        }
        
        /* Sidebar styling */
        section[data-testid="stSidebar"] {
            background: #1a1f2e !important;
            border-right: 1px solid #2d3748 !important;
        }
        section[data-testid="stSidebar"] .stMarkdown {
            color: #e2e8f0 !important;
        }
        section[data-testid="stSidebar"] h1,
        section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3 {
            color: #90cdf4 !important;
        }
        
        /* Text and headings */
        h1, h2, h3, h4, h5, h6 {
            color: #e2e8f0 !important;
        }
        p, label, span, div {
            color: #cbd5e0 !important;
        }
        .stMarkdown {
            color: #cbd5e0 !important;
        }
        
        /* Code blocks */
        code {
            background: #1a202c !important;
            color: #90cdf4 !important;
            padding: 2px 6px !important;
            border-radius: 4px !important;
            border: 1px solid #2d3748 !important;
        }
        pre {
            background: #1a202c !important;
            border: 1px solid #2d3748 !important;
            border-radius: 8px !important;
        }
        
        /* Expander styling */
        .streamlit-expanderHeader {
            background: #1a1f2e !important;
            color: #e2e8f0 !important;
            border: 1px solid #2d3748 !important;
            border-radius: 8px !important;
        }
        .streamlit-expanderContent {
            background: #1a1f2e !important;
            border: 1px solid #2d3748 !important;
            border-left: 3px solid #667eea !important;
        }
        
        /* Divider */
        hr {
            border: none !important;
            border-top: 1px solid #2d3748 !important;
            margin: 1.5rem 0 !important;
        }
        
        /* Info boxes - override inline styles */
        div[style*="background-color: #f0f8ff"],
        div[style*="background-color: #fff3cd"] {
            background: linear-gradient(135deg, #1e3a5f 0%, #0f2744 100%) !important;
            border-left: 4px solid #3182ce !important;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3) !important;
        }
        div[style*="background-color: #f0f8ff"] h4,
        div[style*="background-color: #f0f8ff"] p,
        div[style*="background-color: #fff3cd"] small,
        div[style*="background-color: #fff3cd"] strong,
        div[style*="background-color: #fff3cd"] em {
            color: #e2e8f0 !important;
        }
        
        /* Caption text */
        .stCaptionContainer {
            color: #718096 !important;
        }
        
        /* Links */
        a {
            color: #63b3ed !important;
            text-decoration: none !important;
        }
        a:hover {
            color: #90cdf4 !important;
            text-decoration: underline !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
