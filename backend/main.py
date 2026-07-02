import os
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
    except Exception as e:
        print(f"Database infrastructure mapping failed: {str(e)}")

@app.get("/api/health")
def health_check():
    return {"status": "online", "engine": "FastAPI Layer"}

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
        
        # Fallback initialization if database pipeline step was cleared
        if not pipeline_steps:
            raise HTTPException(status_code=400, detail="Pipeline Execution Fault. Trace: No active steps inside dynamic_pipeline matrix.")

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

# ====================================================
# ADMINISTRATIVE METADATA ROUTING CHANNELS
# ====================================================

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
