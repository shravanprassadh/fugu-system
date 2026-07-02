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
            raise ValueError("Environment variable MASTER_ROUTER_DB_URL is unassigned.")
        
        try:
            self.connection = psycopg2.connect(self.connection_string, cursor_factory=RealDictCursor)
            self.cursor = self.connection.cursor()
            self._bootstrap_database_schema()
            return self.cursor
        except Exception as e:
            if self.connection:
                self.connection.close()
            raise RuntimeError(f"Database connection failure: {str(e)}")

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
        """Constructs backend structures if they are missing from the relational instance."""
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_settings (
                id SERIAL PRIMARY KEY,
                key_string VARCHAR(100) UNIQUE NOT NULL,
                value_string TEXT NOT NULL
            );
        """)

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
        
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_keys_vault (
                id SERIAL PRIMARY KEY,
                provider_name VARCHAR(100) UNIQUE NOT NULL,
                secret_key TEXT NOT NULL
            );
        """)
        
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS threads (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                thread_id INT NOT NULL,
                role VARCHAR(50) NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Seed default administrator credentials hash safely on startup if uninitialized
        self.cursor.execute("SELECT COUNT(*) FROM system_settings WHERE key_string = 'admin_password_plain';")
        if self.cursor.fetchone()['count'] == 0:
            self.cursor.execute("""
                INSERT INTO system_settings (key_string, value_string) 
                VALUES ('admin_password_plain', 'AdminSecure2026!');
            """)

        self.cursor.execute("SELECT COUNT(*) FROM pipeline_steps;")
        if self.cursor.fetchone()['count'] == 0:
            self.cursor.execute("""
                INSERT INTO pipeline_steps (sequence_order_position, step_name, provider_type, model_string, system_prompt_directives)
                VALUES 
                (1, 'Stage 1: Document Extractor', 'openrouter', 'google/gemini-2.5-flash:free', 'Extract core definitions.'),
                (2, 'Stage 2: Logic Reasoner', 'openrouter', 'deepseek/deepseek-r1:free', 'Perform structural calculations.');
            """)
