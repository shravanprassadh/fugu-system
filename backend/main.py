import os
import json
import asyncio
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List
from core.database import ClusterContextRouter

app = FastAPI()

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

# --- Core Streaming Pipeline ---
async def token_stream_generator(thread_id, content):
    with ClusterContextRouter("transactional") as cursor:
        cursor.execute("SELECT id, step_name, provider_type, model_string, system_prompt_directives FROM pipeline_steps ORDER BY sequence_order_position ASC;")
        steps = cursor.fetchall()
    
    if not steps:
        yield f"data: {json.dumps({'error': 'No operational pipeline steps configured in your database.'})}\n\n"
        return

    current_input = content
    for step in steps:
        yield f"data: {json.dumps({'status': f'⚡ [Executing] {step[1]}...'})}\n\n"
        await asyncio.sleep(0.4)
        
        simulated_response = f" [Processed via {step[3]}]"
        for chunk in simulated_response.split(" "):
            if chunk:
                yield f"data: {json.dumps({'token': chunk + ' '})}\n\n"
                await asyncio.sleep(0.05)
        
        current_input += simulated_response
        yield f"data: {json.dumps({'status': f'✅ [Completed] {step[1]}'})}\n\n"

    with ClusterContextRouter("transactional") as cursor:
        cursor.execute("INSERT INTO messages (thread_id, role, content) VALUES (%s, 'user', %s);", (thread_id, content))
        cursor.execute("INSERT INTO messages (thread_id, role, content) VALUES (%s, 'assistant', %s);", (thread_id, current_input))
    yield "data: [DONE]\n\n"

@app.post("/api/chat/stream")
async def stream_chat(payload: MsgPayload = Body(...)):
    return StreamingResponse(token_stream_generator(payload.thread_id, payload.content), media_type="text/event-stream")

# --- Administrative Configuration Endpoints ---
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
            cursor.execute(
                "INSERT INTO pipeline_steps (sequence_order_position, step_name, provider_type, model_string, system_prompt_directives) VALUES (%s, %s, %s, %s, %s);",
                (step.sequence_order_position, step.step_name, step.provider_type, step.model_string, step.system_prompt_directives)
            )
    return {"status": "success", "message": "Pipeline configuration matrix updated."}

@app.get("/api/health")
def health_check():
    return {"status": "healthy"}
