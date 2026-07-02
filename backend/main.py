import os
import json
import asyncio
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

app = FastAPI(title="Fugu Streaming Gateway")

# Enable CORS for frontend cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_URL = os.environ.get("MASTER_ROUTER_DB_URL")

def get_db_cursor():
    if not DB_URL:
        raise ValueError("MASTER_ROUTER_DB_URL environment variable is missing.")
    conn = psycopg2.connect(DB_URL, cursor_factory=RealDictCursor)
    conn.autocommit = True
    return conn, conn.cursor()

class MsgPayload(BaseModel):
    thread_id: int
    content: str

async def token_stream_generator(thread_id: int, content: str):
    """
    Simulates a multi-stage data validation pipeline, 
    streaming real-time phase updates and text tokens to the UI.
    """
    stages = [
        {"name": "Stage 1: Document Extractor", "reply": "Extracted document layout text successfully. "},
        {"name": "Stage 2: Logic Reasoner", "reply": "Deep reasoning analysis complete. No core discrepancies found. "},
        {"name": "Stage 3: Integrity Auditor", "reply": "Data integrity verified against cross-cluster tables. "},
        {"name": "Stage 4: Final Consolidator", "reply": "Here is your audited, clean report summary."}
    ]
    
    # Log incoming user message to database
    try:
        conn, cursor = get_db_cursor()
        cursor.execute(
            "INSERT INTO messages (thread_id, role, content) VALUES (%s, 'user', %s);",
            (thread_id, content)
        )
    except Exception as e:
        yield f"data: {json.dumps({'error': f'Database log error: {str(e)}'})}\n\n"

    full_response = ""
    
    # Process each stage sequentially, but stream tokens asynchronously
    for stage in stages:
        yield f"data: {json.dumps({'status': f'Running {stage[\"name\"]}'})}\n\n"
        await asyncio.sleep(0.6)  # Simulate processing delay between pipeline tasks
        
        words = stage["reply"].split(" ")
        for word in words:
            if word:
                token = word + " "
                full_response += token
                yield f"data: {json.dumps({'token': token})}\n\n"
                await asyncio.sleep(0.04)  # Natural typing rhythm cadence
    
    # Log complete assistant text response to thread database history
    try:
        cursor.execute(
            "INSERT INTO messages (thread_id, role, content) VALUES (%s, 'assistant', %s);",
            (thread_id, full_response)
        )
        cursor.close()
        conn.close()
    except:
        pass

    yield "data: [DONE]\n\n"

@app.post("/api/chat/stream")
async def stream_chat(payload: MsgPayload = Body(...)):
    return StreamingResponse(
        token_stream_generator(payload.thread_id, payload.content),
        media_type="text/event-stream"
    )

@app.get("/api/chat/threads")
def get_threads():
    try:
        conn, cursor = get_db_cursor()
        cursor.execute("SELECT id, name FROM threads ORDER BY id DESC;")
        r = cursor.fetchall()
        cursor.close()
        conn.close()
        return r
    except:
        return []

@app.post("/api/chat/threads")
def create_thread(payload: dict = Body(...)):
    try:
        conn, cursor = get_db_cursor()
        cursor.execute("INSERT INTO threads (name) VALUES (%s) RETURNING id, name;", (payload.get("name", "New Chat"),))
        r = cursor.fetchone()
        cursor.close()
        conn.close()
        return r
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/chat/messages/{thread_id}")
def get_messages(thread_id: int):
    try:
        conn, cursor = get_db_cursor()
        cursor.execute("SELECT role, content FROM messages WHERE thread_id = %s ORDER BY id ASC;", (thread_id,))
        r = cursor.fetchall()
        cursor.close()
        conn.close()
        return r
    except:
        return []
        
@app.get("/api/health")
def health_check():
    return {"status": "healthy"}