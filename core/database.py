import os
import hashlib
import psycopg2
from psycopg2.extras import RealDictCursor
import streamlit as st

@st.cache_resource
def get_router_db():
    return psycopg2.connect(os.environ.get("MASTER_ROUTER_DB_URL"))

def run_query(query, params=None, is_select=True):
    conn = get_router_db()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, params or ())
        if not is_select:
            conn.commit()
            return None
        return cur.fetchall()

def initialize_infra():
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
    run_query(f"INSERT INTO system_settings (key, value) VALUES ('admin_password_hash', '{hashlib.sha256('AdminSecure2026!'.encode()).hexdigest()}') ON CONFLICT DO NOTHING;", is_select=False)
    
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
    return response.choices[0].message.content"""
        run_query("""
            INSERT INTO dynamic_pipeline (step_num, step_name, provider_identifier, model_string, system_prompt, python_code_body)
            VALUES (1, 'The Thinker', 'openrouter', 'openrouter/free', 'You are a helpful assistant.', %s)
            ON CONFLICT DO NOTHING;
        """, (default_code,), is_select=False)

class ClusterContextRouter:
    def __init__(self, op_type):
        db_matrix = {row['operation']: row['connection_string'] for row in run_query("SELECT * FROM db_routing_matrix;")}
        self.target_url = db_matrix.get(op_type, os.environ.get("MASTER_ROUTER_DB_URL"))
        self.conn = None
    def __enter__(self):
        self.conn = psycopg2.connect(self.target_url)
        return self.conn
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn: self.conn.close()
