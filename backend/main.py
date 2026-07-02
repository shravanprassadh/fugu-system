import os
import hashlib
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from core.database import run_query, initialize_infra, ClusterContextRouter
from core.pipeline import execute_pipeline_step

app = FastAPI(title="Sovereign API Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_event():
    try:
        initialize_infra()
        run_query("INSERT INTO system_settings (key, value) VALUES ('admin_username', 'admin') ON CONFLICT DO NOTHING;", is_select=False)
    except Exception as e:
        print(f"Database infrastructure mapping failed: {str(e)}")

@app.get("/api/health")
def health_check():
    return {"status": "online", "engine": "FastAPI Layer"}

# ====================================================
# IDENTITY AND SECURITY AUTHENTICATION HANDSHAKE
# ====================================================

class LoginPayload(BaseModel):
    username: str
    password_hash: str

@app.post("/api/auth/login")
def verify_cluster_access(payload: LoginPayload):
    try:
        stored_user = run_query("SELECT value FROM system_settings WHERE key = 'admin_username';")
        stored_hash = run_query("SELECT value FROM system_settings WHERE key = 'admin_password_hash';")
        user_match = stored_user[0]['value'] == payload.username if stored_user else (payload.username == "admin")
        hash_match = stored_hash[0]['value'] == payload.password_hash if stored_hash else False
        if user_match and hash_match:
            return {"status": "authenticated"}
        raise HTTPException(status_code=401, detail="Invalid cryptographic signature.")
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))

class CredentialsUpdate(BaseModel):
    new_username: str
    new_password_raw: str

@app.post("/api/admin/credentials")
def update_gate_credentials(payload: CredentialsUpdate):
    try:
        if len(payload.new_username.strip()) < 3 or len(payload.new_password_raw.strip()) < 6:
            raise HTTPException(status_code=400, detail="Credentials fail length constraints.")
        new_hash = hashlib.sha256(payload.new_password_raw.encode()).hexdigest()
        run_query("UPDATE system_settings SET value = %s WHERE key = 'admin_username';", (payload.new_username,), is_select=False)
        run_query("UPDATE system_settings SET value = %s WHERE key = 'admin_password_hash';", (new_hash,), is_select=False)
        return {"status": "success"}
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))

# ====================================================
# API KEY VAULT CRUD STATION
# ====================================================

class ApiKeyPayload(BaseModel):
    provider_identifier: str
    api_key: str

@app.get("/api/admin/keys")
def get_vault_keys():
    try:
        vault_rows = run_query("SELECT provider_identifier, api_key FROM api_keys_vault ORDER BY provider_identifier ASC;")
        obfuscated_vault = []
        for row in vault_rows:
            raw = row['api_key'].strip()
            masked = f"{raw[:5]}...{raw[-4:]}" if len(raw) > 10 else "***********"
            obfuscated_vault.append({
                "provider_identifier": row['provider_identifier'],
                "api_key": masked
            })
        return {"keys": obfuscated_vault}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/admin/keys")
def save_vault_key(payload: ApiKeyPayload):
    try:
        provider = payload.provider_identifier.strip().lower()
        key_value = payload.api_key.strip()
        if not provider or not key_value:
            raise HTTPException(status_code=400, detail="Identifier and Key fields are mandatory.")
        run_query("""
            INSERT INTO api_keys_vault (provider_identifier, api_key)
            VALUES (%s, %s)
            ON CONFLICT (provider_identifier) DO UPDATE SET api_key = EXCLUDED.api_key;
        """, (provider, key_value), is_select=False)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/admin/keys/{provider_identifier}")
def delete_vault_key(provider_identifier: str):
    try:
        run_query("DELETE FROM api_keys_vault WHERE provider_identifier = %s;", (provider_identifier.strip().lower(),), is_select=False)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ====================================================
# CHAT CONVERSATION LOGS AND STEP ROUTING
# ====================================================

@app.get("/api/threads")
def get_all_threads():
    try:
        run_query("CREATE TABLE IF NOT EXISTS threads (id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL);", is_select=False)
        threads = run_query("SELECT * FROM threads ORDER BY id DESC;")
        return {"threads": threads}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class ThreadCreate(BaseModel):
    name: str

@app.post("/api/threads")
def create_new_thread(thread: ThreadCreate):
    try:
        run_query("INSERT INTO threads (name) VALUES (%s) ON CONFLICT DO NOTHING;", (thread.name,), is_select=False)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/threads/{thread_id}")
def delete_chat_thread(thread_id: int):
    try:
        with ClusterContextRouter("messages") as db:
            with db.cursor() as cur:
                cur.execute("DELETE FROM messages WHERE thread_id = %s;", (thread_id,))
                db.commit()
        with ClusterContextRouter("threads") as db:
            with db.cursor() as cur:
                cur.execute("DELETE FROM threads WHERE id = %s;", (thread_id,))
                db.commit()
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/threads/{thread_id}/messages")
def get_thread_messages(thread_id: int):
    try:
        with ClusterContextRouter("messages") as db:
            from psycopg2.extras import RealDictCursor
            with db.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("CREATE TABLE IF NOT EXISTS messages (id SERIAL PRIMARY KEY, thread_id INT, role TEXT, content TEXT);")
                db.commit()
                cur.execute("SELECT role, content FROM messages WHERE thread_id = %s ORDER BY id ASC;", (thread_id,))
                return {"messages": cur.fetchall()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class ChatPayload(BaseModel):
    thread_id: int
    prompt: str

@app.post("/api/chat")
def process_workspace_chat(payload: ChatPayload):
    try:
        with ClusterContextRouter("messages") as db:
            with db.cursor() as cur:
                cur.execute("INSERT INTO messages (thread_id, role, content) VALUES (%s, 'user', %s);", (payload.thread_id, payload.prompt))
                db.commit()

        pipeline_steps = run_query("SELECT * FROM dynamic_pipeline ORDER BY step_num ASC;")
        if not pipeline_steps:
            raise HTTPException(status_code=400, detail="Pipeline Execution Fault: No active steps inside dynamic_pipeline matrix.")

        current_response = payload.prompt
        for step in pipeline_steps:
            current_response = execute_pipeline_step(step, current_response)
            if "Security Halt" in current_response or "Pipeline Execution Fault" in current_response:
                raise HTTPException(status_code=400, detail=current_response)

        with ClusterContextRouter("messages") as db:
            with db.cursor() as cur:
                cur.execute("INSERT INTO messages (thread_id, role, content) VALUES (%s, 'assistant', %s);", (payload.thread_id, current_response))
                db.commit()

        return {"role": "assistant", "content": current_response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/admin/config")
def get_cluster_configurations():
    try:
        pipeline = run_query("SELECT * FROM dynamic_pipeline ORDER BY step_num ASC;")
        relays = run_query("SELECT * FROM db_routing_matrix;")
        return {"pipeline": pipeline, "relays": relays}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class PipelineStepUpdate(BaseModel):
    step_num: int
    step_name: str
    provider_identifier: str
    model_string: str
    system_prompt: str
    python_code_body: str

@app.post("/api/admin/pipeline")
def save_pipeline_directives(step: PipelineStepUpdate):
    try:
        from core.pipeline import verify_code_safety
        if not verify_code_safety(step.python_code_body):
            raise HTTPException(status_code=400, detail="Security Halt: Ast evaluation rejected raw code parameters.")
        run_query("""
            INSERT INTO dynamic_pipeline (step_num, step_name, provider_identifier, model_string, system_prompt, python_code_body)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (step_num) DO UPDATE SET 
                step_name = EXCLUDED.step_name, provider_identifier = EXCLUDED.provider_identifier,
                model_string = EXCLUDED.model_string, system_prompt = EXCLUDED.system_prompt, python_code_body = EXCLUDED.python_code_body;
        """, (step.step_num, step.step_name, step.provider_identifier, step.model_string, step.system_prompt, step.python_code_body), is_select=False)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class RelayUpdate(BaseModel):
    threads_url: str
    messages_url: str

@app.post("/api/admin/relays")
def save_relay_targets(relays: RelayUpdate):
    try:
        run_query("INSERT INTO db_routing_matrix (operation, connection_string) VALUES ('threads', %s) ON CONFLICT (operation) DO UPDATE SET connection_string = EXCLUDED.connection_string;", (relays.threads_url,), is_select=False)
        run_query("INSERT INTO db_routing_matrix (operation, connection_string) VALUES ('messages', %s) ON CONFLICT (operation) DO UPDATE SET connection_string = EXCLUDED.connection_string;", (relays.messages_url,), is_select=False)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
