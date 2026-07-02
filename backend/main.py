import os
import json
import asyncio
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
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

async def token_stream_generator(thread_id, content):
    # Establish dynamic database connection and verify active steps
    with ClusterContextRouter("transactional") as cursor:
        cursor.execute("SELECT id, step_name, provider_type, model_string, system_prompt_directives FROM pipeline_steps ORDER BY sequence_order_position ASC;")
        steps = cursor.fetchall()
    
    if not steps:
        yield f"data: {json.dumps({'error': 'No operational pipeline steps configured in your database.'})}\n\n"
        return

    current_input = content
    # For now, we simulate streaming handoffs across the pipeline structure
    for step in steps:
        yield f"data: {json.dumps({'status': f'⚡ [Executing] {step[1]}...'})}\n\n"
        await asyncio.sleep(0.5) # Slight pause for network handoff visual
        
        # Simulate chunk generation for the active model
        simulated_response = f" [Streamed response from {step[3]} processing input: '{current_input[:20]}...']"
        for chunk in simulated_response.split(" "):
            if chunk:
                yield f"data: {json.dumps({'token': chunk + ' '})}\n\n"
                await asyncio.sleep(0.08) # Simulating natural typing speed
        
        current_input += simulated_response
        yield f"data: {json.dumps({'status': f'✅ [Completed] {step[1]}'})}\n\n"

    # Commit the finalized message to the transactional log database
    with ClusterContextRouter("transactional") as cursor:
        cursor.execute(
            "INSERT INTO messages (thread_id, role, content) VALUES (%s, 'user', %s);",
            (thread_id, content)
        )
        cursor.execute(
            "INSERT INTO messages (thread_id, role, content) VALUES (%s, 'assistant', %s);",
            (thread_id, current_input)
        )
    yield "data: [DONE]\n\n"

@app.post("/api/chat/stream")
async def stream_chat(payload: MsgPayload = Body(...)):
    # Simple validation path
    with ClusterContextRouter("master") as cursor:
        cursor.execute("SELECT value_string FROM system_settings WHERE key_string = 'admin_password_hash';")
        db_hash = cursor.fetchone()
        if not db_hash or db_hash[0] != payload.password_hash:
            raise HTTPException(status_code=401, detail="Unauthorized system access signature.")

    return StreamingResponse(
        token_stream_generator(payload.thread_id, payload.content),
        media_type="text/event-stream"
    )

@app.get("/api/health")
def health_check():
    try:
        with ClusterContextRouter("master") as cursor:
            cursor.execute("SELECT 1;")
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
