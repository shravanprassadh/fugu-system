import os
import json
import asyncio
from fastapi import FastAPI, HTTPException, Body, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Optional
from core.database import ClusterContextRouter

app = FastAPI(title="Sovereign Core API Gateway", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Pydantic Data Matrix Schemas ---
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

class CredentialPayload(BaseModel):
    username: str
    new_password_hash: str

# --- Core Asynchronous Real-Time Transport (SSE) ---
async def token_stream_generator(thread_id: int, content: str):
    try:
        with ClusterContextRouter("transactional") as cursor:
            cursor.execute("""
                SELECT sequence_order_position, step_name, provider_type, model_string, system_prompt_directives 
                FROM pipeline_steps 
                ORDER BY sequence_order_position ASC;
            """)
            steps = cursor.fetchall()
    except Exception as e:
        yield f"data: {json.dumps({'error': f'Database lookup fault: {str(e)}'})}\n\n"
        return

    if not steps:
        yield f"data: {json.dumps({'error': 'No operational pipeline processing nodes found in database.'})}\n\n"
        return

    current_input = content
    
    # Cascade text processing across the configured sequence steps
    for step in steps:
        pos, step_name, provider, model_string, directives = step
        yield f"data: {json.dumps({'status': f'⚡ [Executing Step {pos}] {step_name} via {model_string}...'})}\n\n"
        await asyncio.sleep(0.4)  # Visual verification pacing
        
        simulated_response = f" [Streamed matrix chunk from {step_name} using {model_string}]"
        for chunk in simulated_response.split(" "):
            if chunk:
                yield f"data: {json.dumps({'token': chunk + ' '})}\n\n"
                await asyncio.sleep(0.06)
        
        current_input += simulated_response
        yield f"data: {json.dumps({'status': f'✅ [Completed] {step_name}'})}\n\n"

    try:
        with ClusterContextRouter("transactional") as cursor:
            cursor.execute("INSERT INTO messages (thread_id, role, content) VALUES (%s, 'user', %s);", (thread_id, content))
            cursor.execute("INSERT INTO messages (thread_id, role, content) VALUES (%s, 'assistant', %s);", (thread_id, current_input))
    except Exception as e:
        yield f"data: {json.dumps({'status': f'⚠️ Log sync failed: {str(e)}'})}\n\n"

    yield "data: [DONE]\n\n"

@app.post("/api/chat/stream")
async def stream_chat(payload: MsgPayload = Body(...)):
    return StreamingResponse(
        token_stream_generator(payload.thread_id, payload.content),
        media_type="text/event-stream"
    )

# --- 1. Pipeline Sequence Configuration Endpoints ---
@app.get("/api/config/pipeline")
def get_pipeline():
    with ClusterContextRouter("master") as cursor:
        cursor.execute("SELECT sequence_order_position, step_name, provider_type, model_string, system_prompt_directives FROM pipeline_steps ORDER BY sequence_order_position ASC;")
        rows = cursor.fetchall()
    return [{"sequence_order_position": r[0], "step_name": r[1], "provider_type": r[2], "model_string": r[3], "system_prompt_directives": r[4]} for r in rows]

@app.post("/api/config/pipeline")
def update_pipeline(steps: List[PipelineStepModel]):
    with ClusterContextRouter("master") as cursor:
        cursor.execute("DELETE FROM pipeline_steps;")
        for step in steps:
            cursor.execute("""
                INSERT INTO pipeline_steps (sequence_order_position, step_name, provider_type, model_string, system_prompt_directives) 
                VALUES (%s, %s, %s, %s, %s);
            """, (step.sequence_order_position, step.step_name, step.provider_type, step.model_string, step.system_prompt_directives))
    return {"status": "success", "message": "Pipeline mapping matrix updated."}

# --- 2. Multi-SQL Relays Connection Endpoints ---
@app.get("/api/config/relays")
def get_db_relays():
    try:
        with ClusterContextRouter("master") as cursor:
            cursor.execute("SELECT operation_type, connection_string FROM db_routing_matrix ORDER BY operation_type ASC;")
            rows = cursor.fetchall()
        if not rows:
            raise Exception("Empty routing database.")
        return [{"operation_type": r[0], "connection_string": r[1]} for r in rows]
    except Exception:
        # Structured fallbacks to protect frontend rendering from breaking if tables are blank
        return [
            {"operation_type": "master", "connection_string": "neon-serverless-router-cluster"},
            {"operation_type": "metadata", "connection_string": "supabase-managed-sidebar-tier"},
            {"operation_type": "transactional", "connection_string": "oracle-autonomous-20gb-archive"}
        ]

@app.post("/api/config/relays")
def update_db_relay(payload: RelayPayload):
    with ClusterContextRouter("master") as cursor:
        cursor.execute("DELETE FROM db_routing_matrix WHERE operation_type = %s;", (payload.operation_type,))
        cursor.execute("INSERT INTO db_routing_matrix (operation_type, connection_string) VALUES (%s, %s);", (payload.operation_type, payload.connection_string))
    return {"status": "success", "message": f"Data route pointer for '{payload.operation_type}' adjusted live."}

# --- 3. API Key Vault Endpoints ---
@app.get("/api/config/vault")
def get_vault_keys():
    try:
        with ClusterContextRouter("master") as cursor:
            cursor.execute("SELECT provider_name, secret_key FROM api_keys_vault ORDER BY provider_name ASC;")
            rows = cursor.fetchall()
        return [{"provider_name": r[0], "secret_key": f"{r[1][:6]}...••••" if len(r[1]) > 6 else "••••••••"} for r in rows]
    except Exception:
        return []

@app.post("/api/config/vault")
def save_vault_key(payload: VaultKeyPayload):
    with ClusterContextRouter("master") as cursor:
        cursor.execute("DELETE FROM api_keys_vault WHERE provider_name = %s;", (payload.provider_name,))
        cursor.execute("INSERT INTO api_keys_vault (provider_name, secret_key) VALUES (%s, %s);", (payload.provider_name, payload.secret_key))
    return {"status": "success", "message": "API key successfully encapsulated inside remote database vault."}

# --- 4. Security Manager Endpoints ---
@app.post("/api/config/security")
def rotate_credentials(payload: CredentialPayload):
    with ClusterContextRouter("master") as cursor:
        cursor.execute("DELETE FROM system_settings WHERE key_string = 'admin_password_hash';")
        cursor.execute("INSERT INTO system_settings (key_string, value_string) VALUES ('admin_password_hash', %s);", (payload.new_password_hash,))
    return {"status": "success", "message": "Master system password hash rotated cleanly."}

@app.get("/api/health")
def health_check():
    return {"status": "healthy", "engine": "operational"}
