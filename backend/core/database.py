import os
import hashlib
import psycopg2
from psycopg2.extras import RealDictCursor

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

class ClusterContextRouter:
    def __init__(self, op_type):
        try:
            db_matrix = {row['operation']: row['connection_string'] for row in run_query("SELECT * FROM db_routing_matrix;")}
        except Exception:
            db_matrix = {}
        self.target_url = db_matrix.get(op_type, os.environ.get("MASTER_ROUTER_DB_URL"))
        self.conn = None
        
    def __enter__(self):
        self.conn = psycopg2.connect(self.target_url)
        return self.conn
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn: 
            self.conn.close()
