# Copyright 2026 Amazon.com and its affiliates; all rights reserved.
# SPDX-License-Identifier: MIT-0

import streamlit as st


def apply_custom_styles():
    """Apply custom CSS styles to the Streamlit app"""
    st.markdown(
        """
        <style>
        /* Main app background */
        body {
            background: #ffffff !important;
        }
        .stApp {
            background: #ffffff !important;
        }
        
        /* Chat input styling */
        .stChatInput {
            background: #f0f4f8 !important;
            border: 1px solid #cbd5e0 !important;
            border-radius: 12px !important;
        }
        .stChatInput input {
            background: #ffffff !important;
            color: #000000 !important;
            border: none !important;
        }
        .stChatInput input::placeholder {
            color: #4a5568 !important;
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
        /* Chat bubbles use light backgrounds with black text. The bubble
           colours are declared !important because the global
           "p, label, span, div { color: ... !important }" rule below also
           matches these divs and their children, and would otherwise win and
           render the conversation in light grey. */
        .user-bubble {
            background: linear-gradient(135deg, #f7fafc 0%, #edf2f7 100%);
            color: #000000;
            border-radius: 16px;
            padding: 0.8rem 1.2rem;
            margin-bottom: 0.5rem;
            display: inline-block;
            border: 1px solid #a0aec0;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
        }
        .assistant-bubble {
            background: linear-gradient(135deg, #ffffff 0%, #f0f7ff 100%);
            color: #000000;
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
            background: linear-gradient(135deg, #ffffff 0%, #f0f7ff 100%);
            color: #1a365d;
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
            color: #2b6cb0;
            animation: cursor-blink 1s infinite;
            margin-left: 2px;
        }

        /* Force black chat text over the global grey text rule, including any
           nested elements Streamlit renders inside the bubble. */
        .user-bubble,
        .user-bubble p,
        .user-bubble span,
        .user-bubble div,
        .user-bubble li,
        .user-bubble strong,
        .user-bubble em,
        .assistant-bubble,
        .assistant-bubble p,
        .assistant-bubble span,
        .assistant-bubble div,
        .assistant-bubble li,
        .assistant-bubble strong,
        .assistant-bubble em {
            color: #000000 !important;
        }
        .thinking-bubble,
        .thinking-bubble span,
        .thinking-bubble div {
            color: #1a365d !important;
        }

        /* Response-time caption: dimmer than the message but still legible on
           a light bubble. Replaces an inline #888 that fell below contrast. */
        .user-bubble .response-time,
        .assistant-bubble .response-time {
            color: #4a5568 !important;
            font-size: 0.9em;
        }

        /* Links inside a bubble need a dark blue; the global link colour is
           tuned for the dark page background. */
        .user-bubble a,
        .assistant-bubble a {
            color: #1a4f8a !important;
            text-decoration: underline !important;
        }

        /* Inline code inside a bubble, which would otherwise keep the
           dark-page treatment and lose contrast. */
        .user-bubble code,
        .assistant-bubble code {
            background: #edf2f7 !important;
            color: #1a365d !important;
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
            background: #f0f4f8 !important;
            border-right: 1px solid #cbd5e0 !important;
        }
        section[data-testid="stSidebar"] .stMarkdown {
            color: #1a202c !important;
        }
        section[data-testid="stSidebar"] h1,
        section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3 {
            color: #1a4f8a !important;
        }
        
        /* Text and headings */
        h1, h2, h3, h4, h5, h6 {
            color: #1a202c !important;
        }
        p, label, span, div {
            color: #000000 !important;
        }
        .stMarkdown {
            color: #000000 !important;
        }
        
        /* Code blocks */
        code {
            background: #edf2f7 !important;
            color: #1a365d !important;
            padding: 2px 6px !important;
            border-radius: 4px !important;
            border: 1px solid #cbd5e0 !important;
        }
        pre {
            background: #edf2f7 !important;
            border: 1px solid #cbd5e0 !important;
            border-radius: 8px !important;
        }
        
        /* Expander styling */
        .streamlit-expanderHeader {
            background: #f0f4f8 !important;
            color: #1a202c !important;
            border: 1px solid #cbd5e0 !important;
            border-radius: 8px !important;
        }
        .streamlit-expanderContent {
            background: #f0f4f8 !important;
            border: 1px solid #cbd5e0 !important;
            border-left: 3px solid #667eea !important;
        }
        
        /* Divider */
        hr {
            border: none !important;
            border-top: 1px solid #cbd5e0 !important;
            margin: 1.5rem 0 !important;
        }
        
        /* Info boxes - override inline styles */
        div[style*="background-color: #f0f8ff"],
        div[style*="background-color: #fff3cd"] {
            background: linear-gradient(135deg, #ebf4ff 0%, #e0edff 100%) !important;
            border-left: 4px solid #3182ce !important;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12) !important;
        }
        div[style*="background-color: #f0f8ff"] h4,
        div[style*="background-color: #f0f8ff"] p,
        div[style*="background-color: #fff3cd"] small,
        div[style*="background-color: #fff3cd"] strong,
        div[style*="background-color: #fff3cd"] em {
            color: #1a202c !important;
        }
        
        /* Caption text */
        .stCaptionContainer {
            color: #4a5568 !important;
        }
        
        /* Links */
        a {
            color: #2b6cb0 !important;
            text-decoration: none !important;
        }
        a:hover {
            color: #1a4f8a !important;
            text-decoration: underline !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
