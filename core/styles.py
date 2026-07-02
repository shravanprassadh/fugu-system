import streamlit as st

def inject_premium_themes():
    st.markdown("""
        <style>
            /* Global Canvas Reset */
            .stApp {
                background-color: #ffffff;
                color: #111827;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            }
            
            /* Sidebar Typography & Layout */
            [data-testid="stSidebar"] {
                background-color: #f9fafb !important;
                border-right: 1px solid #f3f4f6 !important;
            }
            [data-testid="stSidebar"] h2 {
                color: #111827 !important;
                font-weight: 600 !important;
                font-size: 16px !important;
                letter-spacing: -0.3px;
            }
            
            /* Custom Chat Layout Architecture (ChatGPT/Gemini Replica) */
            .workspace-container {
                max-width: 800px;
                margin: 0 auto;
                padding: 10px 20px;
            }
            
            .chat-bubble {
                display: flex;
                padding: 24px 0;
                margin: 0 auto;
                max-width: 800px;
                border-bottom: 1px solid #f3f4f6;
            }
            
            .avatar-zone {
                width: 32px;
                height: 32px;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-weight: 600;
                font-size: 13px;
                margin-right: 20px;
                flex-shrink: 0;
            }
            
            .avatar-user {
                background-color: #f3f4f6;
                color: #4b5563;
            }
            
            .avatar-core {
                background-color: #eff6ff;
                color: #2563eb;
            }
            
            .content-zone {
                flex-grow: 1;
                color: #1f2937;
                font-size: 15.5px;
                line-height: 1.65;
                word-break: break-word;
            }
            
            .content-zone p {
                margin: 0 0 12px 0;
            }
            
            /* Clean Code Block Overrides */
            pre {
                background-color: #f8fafc !important;
                border: 1px solid #e2e8f0 !important;
                border-radius: 8px !important;
                padding: 16px !important;
                margin: 16px 0 !important;
            }
            code {
                font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace !important;
                font-size: 14px !important;
                color: #0f172a !important;
            }
            
            /* Input Box Fixes */
            .stChatInputContainer {
                background-color: #ffffff !important;
                border-top: none !important;
                padding-bottom: 30px !important;
            }
            .stChatInputContainer > div {
                border: 1px solid #e5e7eb !important;
                border-radius: 24px !important;
                box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05) !important;
                padding: 4px 12px !important;
                background-color: #ffffff !important;
            }
            
            /* Hide Default Streamlit Clutter */
            #MainMenu, footer, header {visibility: hidden;}
            [data-testid="stHeader"] {background: rgba(0,0,0,0) !important;}
        </style>
    """, unsafe_allow_html=True)
