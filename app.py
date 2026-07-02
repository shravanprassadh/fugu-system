import io
import csv
import hashlib
import streamlit as st
from core.database import run_query, initialize_infra, ClusterContextRouter
from core.pipeline import execute_pipeline_step
from core.styles import inject_premium_themes

# 1. Initialize Frame and Premium Presentation Layers
inject_premium_themes()

if "authenticated" not in st.session_state: st.session_state.authenticated = False
if "view_mode" not in st.session_state: st.session_state.view_mode = "chat"

try:
    initialize_infra()
except Exception as e:
    st.error(f"Infrastructure Offline: Database connection dropped: {str(e)}")
    st.stop()

current_settings = {row['key']: row['value'] for row in run_query("SELECT * FROM system_settings;")}
db_matrix = {row['operation']: row['connection_string'] for row in run_query("SELECT * FROM db_routing_matrix;")}

# ====================================================
# SIDEBAR CONTROL STRATUM
# ====================================================
with st.sidebar:
    st.markdown("<h2 style='margin-top: 15px; margin-bottom: 25px;'>✨ Sovereign Canvas</h2>", unsafe_allow_html=True)
    
    new_topic = st.text_input("New Thread Name:", placeholder="New Chat...", label_visibility="collapsed")
    if st.button("➕ New Chat", use_container_width=True) and new_topic:
        with ClusterContextRouter("threads") as db:
            with db.cursor() as cur:
                cur.execute("INSERT INTO threads (name) VALUES (%s) ON CONFLICT DO NOTHING;", (new_topic,))
                db.commit()
        st.session_state.view_mode = "chat"
        st.rerun()
        
    st.markdown("<div style='margin-bottom: 20px;'></div>", unsafe_allow_html=True)
    
    with ClusterContextRouter("threads") as db:
        from psycopg2.extras import RealDictCursor
        with db.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("CREATE TABLE IF NOT EXISTS threads (id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL);")
            db.commit()
            cur.execute("SELECT * FROM threads ORDER BY id DESC;")
            all_threads = cur.fetchall()

    if all_threads:
        for thread in all_threads:
            if st.button(f"💬 {thread['name']}", use_container_width=True, key=f"t_{thread['id']}", type="secondary"):
                st.session_state.active_thread_name = thread['name']
                st.session_state.active_thread_id = thread['id']
                st.session_state.view_mode = "chat"
                st.rerun()
        if "active_thread_id" not in st.session_state:
            st.session_state.active_thread_name = all_threads[0]['name']
            st.session_state.active_thread_id = all_threads[0]['id']
    else:
        st.caption("No active tracks.")

    st.markdown("<div style='height: 40vh;'></div>", unsafe_allow_html=True)
    if st.button("⚙️ Advanced Settings", use_container_width=True):
        st.session_state.view_mode = "admin"
        st.rerun()

# ====================================================
# HIGH-FIDELITY MAIN CANVAS
# ====================================================
if st.session_state.view_mode == "chat":
    if "active_thread_id" not in st.session_state:
        st.info("Initialize a track in the sidebar to begin.")
        st.stop()
        
    active_name = st.session_state.active_thread_name
    active_id = st.session_state.active_thread_id

    # Title Layer
    st.markdown(f"<div class='workspace-container'><h1 style='font-size: 22px; font-weight: 500; color: #111827; margin-bottom:0;'>{active_name}</h1></div>", unsafe_allow_html=True)
    
    with ClusterContextRouter("messages") as db:
        from psycopg2.extras import RealDictCursor
        with db.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("CREATE TABLE IF NOT EXISTS messages (id SERIAL PRIMARY KEY, thread_id INT, role TEXT, content TEXT);")
            db.commit()
            cur.execute("SELECT role, content FROM messages WHERE thread_id = %s ORDER BY id ASC;", (active_id,))
            history = cur.fetchall()

    # Custom Clean Chat Rendering Matrix
    for msg in history:
        is_user = msg['role'] == 'user'
        avatar_label = "U" if is_user else "AI"
        avatar_class = "avatar-user" if is_user else "avatar-core"
        
        st.markdown(f"""
            <div class='chat-bubble'>
                <div class='avatar-zone {avatar_class}'>{avatar_label}</div>
                <div class='content-zone'>{msg['content']}</div>
            </div>
        """, unsafe_allow_html=True)

    # Input Dock Execution
    user_prompt = st.chat_input("Message your sovereign core...")

    if user_prompt:
        # Display user input immediately
        st.markdown(f"""
            <div class='chat-bubble'>
                <div class='avatar-zone avatar-user'>U</div>
                <div class='content-zone'>{user_prompt}</div>
            </div>
        """, unsafe_allow_html=True)
        
        with ClusterContextRouter("messages") as db:
            with db.cursor() as cur:
                cur.execute("INSERT INTO messages (thread_id, role, content) VALUES (%s, 'user', %s);", (active_id, user_prompt))
                db.commit()

        pipeline_steps = run_query("SELECT * FROM dynamic_pipeline ORDER BY step_num ASC;")
        current_payload = user_prompt

        # Container for Assistant Response
        status_indicator = st.empty()
        status_indicator.markdown("<div class='chat-bubble'><div class='avatar-zone avatar-core'>AI</div><div class='content-zone' style='color:#6b7280;'>⚡ Generating response...</div></div>", unsafe_allow_html=True)
        
        for step in pipeline_steps:
            current_payload = execute_pipeline_step(step, current_payload)
            if "Security Halt" in current_payload or "Pipeline Execution Fault" in current_payload:
                status_indicator.empty()
                st.error(current_payload)
                st.stop()

        status_indicator.empty()
        
        # Render clean finalized assistant output bubble
        st.markdown(f"""
            <div class='chat-bubble'>
                <div class='avatar-zone avatar-core'>AI</div>
                <div class='content-zone'>{current_payload}</div>
            </div>
        """, unsafe_allow_html=True)
            
        with ClusterContextRouter("messages") as db:
            with db.cursor() as cur:
                cur.execute("INSERT INTO messages (thread_id, role, content) VALUES (%s, 'assistant', %s);", (active_id, current_payload))
                db.commit()
        st.rerun()

# ====================================================
# BACKEND TERMINAL
# ====================================================
elif st.session_state.view_mode == "admin":
    if not st.session_state.authenticated:
        st.markdown("<div style='max-width: 400px; margin: 100px auto; padding: 30px; border: 1px solid #e5e7eb; border-radius:12px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);'>", unsafe_allow_html=True)
        st.subheader("🔒 Infrastructure Gate")
        pass_attempt = st.text_input("Enter Control Passphrase:", type="password")
        if st.button("Unlock Core Matrix", type="primary", use_container_width=True):
            if hashlib.sha256(pass_attempt.encode()).hexdigest() == current_settings["admin_password_hash"]:
                st.session_state.authenticated = True
                st.rerun()
            else: st.error("Passphrase verification failed.")
        if st.button("← Return to Canvas", use_container_width=True):
            st.session_state.view_mode = "chat"
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)
        st.stop()

    st.title("🛠️ System Configuration Console")
    infra_tab, pipeline_tab, migrate_tab = st.tabs(["🌐 Server Relays", "⛓️ Step Router", "🔄 Data Pump"])
    
    with pipeline_tab:
        st.subheader("Active Pipeline Sequences")
        active_topology = run_query("SELECT step_num, step_name, provider_identifier, model_string FROM dynamic_pipeline ORDER BY step_num ASC;")
        st.dataframe(active_topology, use_container_width=True)
        
        col_a, col_b = st.columns(2)
        with col_a:
            step_pos = st.number_input("Sequence Order Position:", min_value=1, value=1)
            step_name = st.text_input("Display Step Name:", value="Sovereign Auto-Core")
            provider_id = st.text_input("API Envoy Prefix:", value="openrouter")
        with col_b:
            model_id = st.text_input("Exact Model String Identifier:", value="openrouter/free")
            sys_prompt = st.text_area("System Prompt Directives:", value="You are a helpful assistant.")
            
        code_body_input = st.text_area("Python Execution Logic:", height=150, value="""def execute_step(payload, system_prompt, model_string, api_key):
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
    response = client.chat.completions.create(
        model=model_string,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content=payload"}
        ]
    )
    return response.choices[0].message.content""")
        
        if st.button("Save Operational Directives", type="primary"):
            from core.pipeline import verify_code_safety
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

    if st.button("Close Admin Session", type="secondary"):
        st.session_state.authenticated = False
        st.session_state.view_mode = "chat"
        st.rerun()
