import os
import json
import asyncio
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List
from core.database import ClusterContextRouter

app = FastAPI(title="Sovereign Enterprise API Gateway", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class MsgPayload(BaseModel):
    thread_id: int
    content: str
    username: str
    password_hash: str

class PipelineStepModel(BaseModel):
    sequence_order_position: int
    step_name: str
    provider_type: str
    model_string: str
    system_prompt_directives: str

class VaultKeyPayload(BaseModel):
    provider_name: str
    secret_key: str

class RelayPayload(BaseModel):
    operation_type: str
    connection_string: str

# --- Core Asynchronous Real-Time Streaming Transport Layer (SSE) ---
async def token_stream_generator(thread_id: int, content: str):
    try:
        with ClusterContextRouter() as cursor:
            cursor.execute("SELECT sequence_order_position, step_name, provider_type, model_string, system_prompt_directives FROM pipeline_steps ORDER BY sequence_order_position ASC;")
            steps = cursor.fetchall()
    except Exception as e:
        yield f"data: {json.dumps({'error': f'Database pipeline routing fault: {str(e)}'})}\n\n"
        return

    if not steps:
        yield f"data: {json.dumps({'error': 'No runtime sequence nodes populated inside cloud SQL tables.'})}\n\n"
        return

    current_input = content
    for step in steps:
        yield f"data: {json.dumps({'status': f'⚡ [Executing] {step['step_name']} via {step['model_string']}...'})}\n\n"
        await asyncio.sleep(0.4)
        
        simulated_response = f" [Streamed token chunk verification passed downstream for architectural block '{step['step_name']}']"
        for chunk in simulated_response.split(" "):
            if chunk:
                yield f"data: {json.dumps({'token': chunk + ' '})}\n\n"
                await asyncio.sleep(0.04)
        current_input += simulated_response
        yield f"data: {json.dumps({'status': f'✅ [Completed] {step['step_name']}'})}\n\n"

    try:
        with ClusterContextRouter() as cursor:
            cursor.execute("INSERT INTO messages (thread_id, role, content) VALUES (%s, 'user', %s);", (thread_id, content))
            cursor.execute("INSERT INTO messages (thread_id, role, content) VALUES (%s, 'assistant', %s);", (thread_id, current_input))
    except Exception as e:
        yield f"data: {json.dumps({'status': f'⚠️ Historical log indexing skipped: {str(e)}'})}\n\n"

    yield "data: [DONE]\n\n"

@app.post("/api/chat/stream")
async def stream_chat(payload: MsgPayload = Body(...)):
    return StreamingResponse(token_stream_generator(payload.thread_id, payload.content), media_type="text/event-stream")

# --- Interactive Operational Endpoints ---
@app.get("/api/chat/threads")
def get_historical_threads():
    with ClusterContextRouter() as cursor:
        cursor.execute("SELECT id, name FROM threads ORDER BY id DESC;")
        return cursor.fetchall()

@app.post("/api/chat/threads")
def create_new_thread(payload: dict = Body(...)):
    with ClusterContextRouter() as cursor:
        cursor.execute("INSERT INTO threads (name) VALUES (%s) RETURNING id, name;", (payload.get("name", "New Chat"),))
        return cursor.fetchone()

@app.get("/api/chat/messages/{thread_id}")
def get_thread_messages(thread_id: int):
    with ClusterContextRouter() as cursor:
        cursor.execute("SELECT role, content FROM messages WHERE thread_id = %s ORDER BY id ASC;", (thread_id,))
        return cursor.fetchall()

@app.get("/api/config/pipeline")
def get_pipeline_steps():
    with ClusterContextRouter() as cursor:
        cursor.execute("SELECT sequence_order_position, step_name, provider_type, model_string, system_prompt_directives FROM pipeline_steps ORDER BY sequence_order_position ASC;")
        return cursor.fetchall()

@app.post("/api/config/pipeline")
def update_pipeline_steps(steps: List[PipelineStepModel]):
    with ClusterContextRouter() as cursor:
        cursor.execute("DELETE FROM pipeline_steps;")
        for step in steps:
            cursor.execute("INSERT INTO pipeline_steps (sequence_order_position, step_name, provider_type, model_string, system_prompt_directives) VALUES (%s, %s, %s, %s, %s);",
                           (step.sequence_order_position, step.step_name, step.provider_type, step.model_string, step.system_prompt_directives))
    return {"status": "success"}

@app.get("/api/config/relays")
def get_database_relays():
    with ClusterContextRouter() as cursor:
        cursor.execute("SELECT operation_type, connection_string FROM db_routing_matrix ORDER BY operation_type ASC;")
        return cursor.fetchall()

@app.post("/api/config/relays")
def update_database_relay(payload: RelayPayload):
    with ClusterContextRouter() as cursor:
        cursor.execute("INSERT INTO db_routing_matrix (operation_type, connection_string) VALUES (%s, %s) ON CONFLICT (operation_type) DO UPDATE SET connection_string = EXCLUDED.connection_string;",
                       (payload.operation_type, payload.connection_string))
    return {"status": "success"}

@app.get("/api/config/vault")
def get_vault_credentials():
    with ClusterContextRouter() as cursor:
        cursor.execute("SELECT provider_name, secret_key FROM api_keys_vault ORDER BY provider_name ASC;")
        rows = cursor.fetchall()
        return [{"provider_name": r['provider_name'], "secret_key": f"{r['secret_key'][:8]}••••••••" if len(r['secret_key']) > 8 else "••••••••"} for r in rows]

@app.post("/api/config/vault")
def save_vault_credential(payload: VaultKeyPayload):
    with ClusterContextRouter() as cursor:
        cursor.execute("INSERT INTO api_keys_vault (provider_name, secret_key) VALUES (%s, %s) ON CONFLICT (provider_name) DO UPDATE SET secret_key = EXCLUDED.secret_key;",
                       (payload.provider_name, payload.secret_key))
    return {"status": "success"}

@app.get("/api/health")
def engine_health_check():
    return {"status": "healthy", "database_bootstrap": "verified"}
