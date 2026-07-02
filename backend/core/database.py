import os
import psycopg2
from psycopg2.extras import RealDictCursor

class ClusterContextRouter:
    def __init__(self, operation_type: str = "master"):
        self.operation_type = operation_type
        self.connection_string = os.environ.get("MASTER_ROUTER_DB_URL")
        self.connection = None
        self.cursor = None

    def __enter__(self):
        if not self.connection_string:
            raise ValueError("Critical Exception: MASTER_ROUTER_DB_URL environment variable is unassigned.")
        
        try:
            # Bind RealDictCursor to explicitly map lowercase SQL fields to frontend JSON keys
            self.connection = psycopg2.connect(self.connection_string, cursor_factory=RealDictCursor)
            self.cursor = self.connection.cursor()
            self._bootstrap_database_schema()
            return self.cursor
        except Exception as e:
            if self.connection:
                self.connection.close()
            raise RuntimeError(f"Data tier connection sequence aborted: {str(e)}")

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            if self.connection:
                self.connection.rollback()
        else:
            if self.connection:
                self.connection.commit()
        
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()

    def _bootstrap_database_schema(self):
        """Constructs and seeds all required relational tables instantly if the instance is blank."""
        # 1. Pipeline Steps Table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS pipeline_steps (
                id SERIAL PRIMARY KEY,
                sequence_order_position INT NOT NULL,
                step_name VARCHAR(255) NOT NULL,
                provider_type VARCHAR(100) NOT NULL,
                model_string VARCHAR(255) NOT NULL,
                system_prompt_directives TEXT
            );
        """)
        
        # 2. Multi-SQL Relays Matrix Table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS db_routing_matrix (
                id SERIAL PRIMARY KEY,
                operation_type VARCHAR(100) UNIQUE NOT NULL,
                connection_string TEXT NOT NULL
            );
        """)
        
        # 3. API Token Vault Storage Table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_keys_vault (
                id SERIAL PRIMARY KEY,
                provider_name VARCHAR(100) UNIQUE NOT NULL,
                secret_key TEXT NOT NULL
            );
        """)
        
        # 4. Chat Threads Directory Table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS threads (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # 5. Cascading Message Blocks Table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                thread_id INT NOT NULL,
                role VARCHAR(50) NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Seed structural operational baseline rows if database registers empty
        self.cursor.execute("SELECT COUNT(*) FROM pipeline_steps;")
        if self.cursor.fetchone()['count'] == 0:
            self.cursor.execute("""
                INSERT INTO pipeline_steps (sequence_order_position, step_name, provider_type, model_string, system_prompt_directives)
                VALUES (1, 'Sovereign Core Ingestion', 'openrouter', 'google/gemini-2.5-flash:free', 'You are an unquantized enterprise intelligence routing gateway container.');
            """)
            
        self.cursor.execute("SELECT COUNT(*) FROM db_routing_matrix;")
        if self.cursor.fetchone()['count'] == 0:
            self.cursor.execute("""
                INSERT INTO db_routing_matrix (operation_type, connection_string) VALUES 
                ('master', 'postgresql://neon_serverless_active_tier_router/master_cluster_db'),
                ('metadata', 'postgresql://supabase_managed_isolated_sidebar/metadata_db'),
                ('transactional', 'postgresql://oracle_autonomous_secure_vault/heavy_payload_logs_db');
            """)
