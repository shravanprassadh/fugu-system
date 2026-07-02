import os
import io
import csv
import ast
import hashlib
import streamlit as st
import psycopg2
from psycopg2.extras import RealDictCursor
import google.generativeai as genai
from openai import OpenAI

# 1. Premium Consumer-Grade Page Configuration
st.set_page_config(page_title="Sovereign Workspace", page_icon="✨", layout="wide", initial_sidebar_state="expanded")

# High-Fidelity Minimalist Light Theme Stylesheet
st.markdown("""
    <style>
        /* Base Application Layout */
        .stApp { background-color: #ffffff; color: #1e293b; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
        [data-testid="stSidebar"] { background-color: #f8fafc !important; border-right: 1px solid #e2e8f0 !important; }
        
        /* Typography Polish */
        h1, h2, h3 { color: #0f172a !important; font-weight: 600 !important; }
        .stCaption { color: #64748b !important; }
        
        /* Modern Inputs and Text Boxes */
        .stTextInput>div>div>input, .stTextArea>div>div>textarea, .stSelectbox>div>div {
            background-color: #f1f5f9 !important; color: #0f172a !important; border: 1px solid #cbd5e1 !important; border-radius: 10px !important; padding: 10px !important;
        }
        .stTextInput>div>div>input:focus { border-color: #3b82f6 !important; box-shadow: 0 0 0 1px #3b82f6 !important; }
        
        /* Clean Environment Toggle Switch */
        div.row-widget.stRadio > div {
            flex-direction: row !important; background-color: #e2e8f0; padding: 4px; border-radius: 8px; border: none;
        }
        div.row-widget.stRadio label[data-baseweb="radio"] div:first-child { display: none !important; }
        div.row-widget.stRadio label {
            background-color: transparent; padding: 6px 14px !important; border-radius: 6px !important; color: #64748b !important; margin: 0px !important; font-weight: 500; transition: all 0.15s ease-in-out;
        }
        div.row-widget.stRadio label:hover { color: #0f172a !important; }
        
        /* Polished Chat Container Bubble Rules */
        .stChatMessage { background-color: #ffffff !important; border: none !important; padding: 16px 8px !important; margin-bottom: 0px !important; border-bottom: 1px solid #f1f5f9 !important; }
        [data-testid="stChatMessageContent"] { color: #334155 !important; font-size: 16px !important; line-height: 1.6 !important; }
    </style>
""", unsafe_allow_html=True)

# Initialize Authentication State Trackers
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

# 2. Relational Database Orchestration Links
@st.cache_resource
def get_router_db():
    return psycopg2.connect(os.environ.get("MASTER_ROUTER_DB_URL"))

try:
    router_conn = get_router_db()
except Exception as e:
    st.error(f"Infrastructure Offline: Connection to underlying data node failed: {str(e)}")
    st.stop()

def run_query(query, params=None, is_select=True):
    with router_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, params or ())
        if not is_select:
            router_conn.commit()
            return None
        return cur.fetchall()

# Initialize Immutable System Framework Tables
run_query("CREATE TABLE IF NOT EXISTS system_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);", is_select=False)
run_query("CREATE TABLE IF NOT EXISTS db_routing_matrix (operation TEXT PRIMARY KEY, connection_string TEXT NOT NULL);", is_select=False)
run_query("""
    CREATE TABLE IF NOT EXISTS dynamic_pipeline (
        step_num INTEGER PRIMARY KEY,
        step_name TEXT NOT NULL,
        provider_identifier TEXT NOT NULL,
        model_string TEXT NOT NULL,
        system_prompt TEXT NOT NULL,
        python_code_body TEXT NOT NULL
    );
""", is_select=False)

# Seed master administrative credentials if table is clean
run_query(f"INSERT INTO system_settings (key, value) VALUES ('admin_password_hash', '{hashlib.sha256('AdminSecure2026!'.encode()).hexdigest()}') ON CONFLICT DO NOTHING;", is_select=False)

# Seed a default out-of-the-box pipeline step if completely empty
pipeline_check = run_query("SELECT * FROM dynamic_pipeline;")
if not pipeline_check:
    default_code = """def execute_step(payload, system_prompt, model_string, api_key):
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
    response = client.chat.completions.create(
        model=model_string,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": payload}
        ]
    )
    return response.choices[0].message.content
"""
    run_query("""
        INSERT INTO dynamic_pipeline (step_num, step_name, provider_identifier, model_string, system_prompt, python_code_body)
        VALUES (1, 'The Thinker', 'openrouter', 'meta-llama/llama-3-8b-instruct:free', 'You are a helpful assistant.', %s)
        ON CONFLICT DO NOTHING;
    """, (default_code,), is_select=False)

current_settings = {row['key']: row['value'] for row in run_query("SELECT * FROM system_settings;")}
db_matrix = {row['operation']: row['connection_string'] for row in run_query("SELECT * FROM db_routing_matrix;")}

class ClusterContextRouter:
    def __init__(self, op_type):
        self.target_url = db_matrix.get(op_type, os.environ.get("MASTER_ROUTER_DB_URL"))
        self.conn = None
    def __enter__(self):
        self.conn = psycopg2.connect(self.target_url)
        return self.conn
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn: self.conn.close()

def verify_code_safety(code_string: str) -> bool:
    try:
        tree = ast.parse(code_string)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)): return False
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in ["eval", "exec", "open", "compile", "globals", "locals", "subprocess"]: return False
        return True
    except Exception:
        return False

# ----------------------------------------------------
# SYSTEM NAVIGATION NAVIGATION BAR
# ----------------------------------------------------
with st.sidebar:
    st.markdown("<h2 style='font-size: 20px; margin-bottom: 0;'>✨ Workspace Canvas</h2>", unsafe_allow_html=True)
    st.caption("Sovereign User Interface")
    st.markdown("<div style='margin-bottom: 12px;'></div>", unsafe_allow_html=True)
    
    app_mode = st.radio("ENVIRONMENT", options=["✨ Chat", "🛠️ Engineering Console"], index=0, label_visibility="collapsed")
    st.divider()

# ====================================================
# ENVIRONMENT A: USER CONVERSATIONAL WORKSPACE
# ====================================================
if app_mode == "✨ Chat":
    with ClusterContextRouter("threads") as db:
        with db.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("CREATE TABLE IF NOT EXISTS threads (id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL);")
            db.commit()
            cur.execute("SELECT * FROM threads ORDER BY id DESC;")
            all_threads = cur.fetchall()

    with st.sidebar:
        st.markdown("<p style='font-weight: 500; font-size: 14px; margin-bottom: 5px; color:#475569;'>Conversations</p>", unsafe_allow_html=True)
        new_topic = st.text_input("New Topic:", placeholder="+ Start new track...", label_visibility="collapsed")
        if st.button("Create Thread", use_container_width=True) and new_topic:
            with ClusterContextRouter("threads") as db:
                with db.cursor() as cur:
                    cur.execute("INSERT INTO threads (name) VALUES (%s) ON CONFLICT DO NOTHING;", (new_topic,))
                    db.commit()
            st.rerun()
        
        st.markdown("<div style='margin-bottom: 15px;'></div>", unsafe_allow_html=True)
        if all_threads:
            active_name = st.radio("Active Tracks:", options=[t['name'] for t in all_threads], label_visibility="collapsed")
            active_id = next(t['id'] for t in all_threads if t['name'] == active_name)
        else:
            st.info("Initialize a track to begin.")
            st.stop()

    # Main Chat Frame Layout
    st.markdown(f"<h1 style='font-size: 26px; font-weight: 600; letter-spacing: -0.5px;'>{active_name}</h1>", unsafe_allow_html=True)
    st.markdown("<hr style='margin-top: 5px; margin-bottom: 25px; border: 0; border-top: 1px solid #f1f5f9;'>", unsafe_allow_html=True)
    
    with ClusterContextRouter("messages") as db:
        with db.cursor(cursor_factory=RealDictCursor) as cur: # Added the dictionary parser here
            cur.execute("CREATE TABLE IF NOT EXISTS messages (id SERIAL PRIMARY KEY, thread_id INT, role TEXT, content TEXT);")
            db.commit()
            cur.execute("SELECT role, content FROM messages WHERE thread_id = %s ORDER BY id ASC;", (active_id,))
            history = cur.fetchall()

    # Render History Using Standard Presentation Models
    for msg in history:
        with st.chat_message(msg['role']): 
            st.markdown(msg['content'])

    user_prompt = st.chat_input("Message your sovereign core...")

    if user_prompt:
        with st.chat_message("user"): st.markdown(user_prompt)
        with ClusterContextRouter("messages") as db:
            with db.cursor() as cur:
                cur.execute("INSERT INTO messages (thread_id, role, content) VALUES (%s, 'user', %s);", (active_id, user_prompt))
                db.commit()

        pipeline_steps = run_query("SELECT * FROM dynamic_pipeline ORDER BY step_num ASC;")
        current_payload = user_prompt

        with st.chat_message("assistant"):
            status_indicator = st.empty()
            
            for step in pipeline_steps:
                status_indicator.markdown(f"<p style='color:#3b82f6; font-size:14px; font-weight:500;'>⚡ Processing operational steps...</p>", unsafe_allow_html=True)
                
                if not verify_code_safety(step['python_code_body']):
                    st.error("Security Halt: Code execution strings failed parameters.")
                    st.stop()
                
                local_scope = {}
                global_scope = {"OpenAI": OpenAI, "genai": genai}
                
                try:
                    exec(step['python_code_body'], global_scope, local_scope)
                    target_api_key = os.environ.get(f"{step['provider_identifier'].upper()}_API_KEY")
                    
                    current_payload = local_scope['execute_step'](
                        payload=current_payload,
                        system_prompt=step['system_prompt'],
                        model_string=step['model_string'],
                        api_key=target_api_key
                    )
                except Exception as e:
                    st.error(f"Pipeline Interrupted. Trace: {str(e)}")
                    st.stop()

            status_indicator.empty()
            st.markdown(current_payload)
            
        with ClusterContextRouter("messages") as db:
            with db.cursor() as cur:
                cur.execute("INSERT INTO messages (thread_id, role, content) VALUES (%s, 'assistant', %s);", (active_id, current_payload))
                db.commit()

# ====================================================
# ENVIRONMENT B: BACKEND ADMINISTRATIVE CONTROL CENTER
# ====================================================
elif app_mode == "🛠️ Engineering Console":
    if not st.session_state.authenticated:
        st.markdown("<div style='max-width: 420px; margin: 80px auto;'>", unsafe_allow_html=True)
        st.subheader("🔒 System Verification Needed")
        pass_attempt = st.text_input("Enter Control Passphrase:", type="password")
        if st.button("Unlock Terminal Matrix", type="primary", use_container_width=True):
            if hashlib.sha256(pass_attempt.encode()).hexdigest() == current_settings["admin_password_hash"]:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Verification match failed.")
        st.markdown("</div>", unsafe_allow_html=True)
        st.stop()

    st.title("🛠️ System Configuration Console")
    infra_tab, pipeline_tab, migrate_tab = st.tabs(["🌐 Server Relays", "⛓️ Step Router", "🔄 Data Pump"])
    
    with pipeline_tab:
        st.subheader("Execution Matrix Settings")
        active_topology = run_query("SELECT step_num, step_name, provider_identifier, model_string FROM dynamic_pipeline ORDER BY step_num ASC;")
        st.dataframe(active_topology, use_container_width=True)
        
        st.markdown("### Modify Operations Chain")
        col_a, col_b = st.columns(2)
        with col_a:
            step_pos = st.number_input("Sequence Order Position:", min_value=1, value=1)
            step_name = st.text_input("Display Step Name:", value="The Thinker")
            provider_id = st.text_input("API Envoy Prefix:", value="openrouter")
        with col_b:
            model_id = st.text_input("Exact Model String Identifier:", value="meta-llama/llama-3-8b-instruct:free")
            sys_prompt = st.text_area("System Prompt Directives:", value="You are a helpful assistant.")
            
        code_body_input = st.text_area("Python Execution Logic:", height=150, value="""def execute_step(payload, system_prompt, model_string, api_key):
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
    response = client.chat.completions.create(
        model=model_string,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": payload}
        ]
    )
    return response.choices[0].message.content""")
        
        if st.button("Save Operational Directives", type="primary"):
            if verify_code_safety(code_body_input):
                run_query("""
                    INSERT INTO dynamic_pipeline (step_num, step_name, provider_identifier, model_string, system_prompt, python_code_body)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (step_num) DO UPDATE SET 
                        step_name = EXCLUDED.step_name, provider_identifier = EXCLUDED.provider_identifier,
                        model_string = EXCLUDED.model_string, system_prompt = EXCLUDED.system_prompt, python_code_body = EXCLUDED.python_code_body;
                """, (step_pos, step_name, provider_id, model_id, sys_prompt, code_body_input), is_select=False)
                st.success("Database parameters modified successfully.")
                st.rerun()

    with infra_tab:
        st.subheader("SQL Cloud Server Allocation Map")
        cx1, cx2 = st.columns(2)
        with cx1: target_t = st.text_input("Metadata Threads SQL Target URI:", value=db_matrix.get("threads", ""))
        with cx2: target_m = st.text_input("Heavy Log Transaction SQL Target URI:", value=db_matrix.get("messages", ""))
        if st.button("Commit Cluster Routing Changes", type="primary"):
            for op, url in [("threads", target_t), ("messages", target_m)]:
                run_query("INSERT INTO db_routing_matrix (operation, connection_string) VALUES (%s, %s) ON CONFLICT (operation) DO UPDATE SET connection_string = EXCLUDED.connection_string;", (op, url), is_select=False)
            st.success("Relay paths updated.")
            st.rerun()

    with migrate_tab:
        st.subheader("Live Cross-Server Migration Pump")
        m_target = st.selectbox("Select Target Table Block to Move:", ["threads", "messages"])
        active_src = db_matrix.get(m_target, os.environ.get("MASTER_ROUTER_DB_URL"))
        new_dest_url = st.text_input("Enter Destination PostgreSQL Connection String:")
        
        if st.button("Execute Zero-Downtime Data Migration", type="primary"):
            if new_dest_url and new_dest_url != active_src:
                with st.spinner("Moving transactional entries..."):
                    try:
                        src_conn = psycopg2.connect(active_src); dest_conn = psycopg2.connect(new_dest_url)
                        src_cur = src_conn.cursor(); dest_cur = dest_conn.cursor()
                        table = "threads" if m_target == "threads" else "messages"
                        
                        if table == "threads": dest_cur.execute("CREATE TABLE IF NOT EXISTS threads (id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL);")
                        else: dest_cur.execute("CREATE TABLE IF NOT EXISTS messages (id SERIAL PRIMARY KEY, thread_id INT, role TEXT, content TEXT);")
                        dest_conn.commit()
                        
                        src_cur.execute(f"SELECT * FROM {table};")
                        records = src_cur.fetchall()
                        if records:
                            buf = io.StringIO(); writer = csv.writer(buf); writer.writerows(records); buf.seek(0)
                            dest_cur.copy_expert(f"COPY {table} FROM STDIN WITH (FORMAT CSV)", buf)
                            dest_conn.commit()
                        
                        src_conn.close(); dest_conn.close()
                        run_query("INSERT INTO db_routing_matrix (operation, connection_string) VALUES (%s, %s) ON CONFLICT (operation) DO UPDATE SET connection_string = EXCLUDED.connection_string;", (m_target, new_dest_url), is_select=False)
                        st.success("Migration copy executed and pointers flipped.")
                        st.rerun()
                    except Exception as err: st.error(f"Error executing cloud copy: {str(err)}")

    if st.button("Lock Console Matrix", type="secondary"):
        st.session_state.authenticated = False
        st.rerun()
