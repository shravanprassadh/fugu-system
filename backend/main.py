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
        print(f"Database infrastructure offline: {str(e)}")

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
        # 1. Log user message to cluster archive
        with ClusterContextRouter("messages") as db:
            with db.cursor() as cur:
                cur.execute("INSERT INTO messages (thread_id, role, content) VALUES (%s, 'user', %s);", (payload.thread_id, payload.prompt))
                db.commit()

        # 2. Extract active execution steps from dynamic pipeline routing table
        pipeline_steps = run_query("SELECT * FROM dynamic_pipeline ORDER BY step_num ASC;")
        current_response = payload.prompt

        # 3. Process data sequentially through your AI modules
        for step in pipeline_steps:
            current_response = execute_pipeline_step(step, current_response)
            if "Security Halt" in current_response or "Pipeline Execution Fault" in current_response:
                raise HTTPException(status_code=400, detail=current_response)

        # 4. Log finalized execution output back to database archive
        with ClusterContextRouter("messages") as db:
            with db.cursor() as cur:
                cur.execute("INSERT INTO messages (thread_id, role, content) VALUES (%s, 'assistant', %s);", (payload.thread_id, current_response))
                db.commit()

        return {"role": "assistant", "content": current_response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
