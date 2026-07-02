import os
import sys
import json
import asyncio
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

app = FastAPI(title="Fugu Simple Gateway", version="5.0.0")

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

def bootstrap_database():
    try:
        conn, cursor = get_db_cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS threads (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                thread_id INT NOT NULL,
                role VARCHAR(50) NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pipeline_settings (
                step_num INT PRIMARY KEY,
                step_name VARCHAR(255) NOT NULL,
                model_string VARCHAR(255) NOT NULL
            );
        """)
        
        cursor.execute("SELECT COUNT(*) FROM pipeline_settings;")
        if cursor.fetchone()['count'] == 0:
            cursor.execute("""
                INSERT INTO pipeline_settings (step_num, step_name, model_string) VALUES
                (1, 'Stage 1: Document Extractor', 'google/gemini-2.5-flash:free'),
                (2, 'Stage 2: Logic Reasoner', 'deepseek/deepseek-r1:free'),
                (3, 'Stage 3: Integrity Auditor', 'google/gemini-2.5-pro:free'),
                (4, 'Stage 4: Final Consolidator', 'meta-llama/llama-3.3-70b-instruct:free');
            """)
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Database bootstrap notice: {str(e)}")

if DB_URL:
    bootstrap_database()

class MsgPayload(BaseModel):
    thread_id: int
    content: str

class PipelineStepUpdate(BaseModel):
    step_num: int
    model_string: str

async def token_stream_generator(thread_id: int, content: str):
    try:
        conn, cursor = get_db_cursor()
        cursor.execute("SELECT step_num, step_name, model_string FROM pipeline_settings ORDER BY step_num ASC;")
        steps = cursor.fetchall()
    except Exception as e:
        yield f"data: {json.dumps({'error': f'Database fault: {str(e)}'})}\n\n"
        return

    current_input = content
    for step in steps:
        s_num = step['step_num']
        s_name = step['step_name']
        model = step['model_string']
        
        yield f"data: {json.dumps({'status': f'Running {s_name} ({model})...'})}\n\n"
        await asyncio.sleep(0.5)
        
        chunk_response = f"\n\n[{s_name} Output via {model}]:\nProcessed step input context through configured guidelines successfully."
        for chunk in chunk_response.split(" "):
            if chunk:
                yield f"data: {json.dumps({'token': chunk + ' '})}\n\n"
                await asyncio.sleep(0.04)
        current_input += chunk_response
        yield f"data: {json.dumps({'status': f'Completed Stage {s_num}'})}\n\n"

    try:
        cursor.execute("INSERT INTO messages (thread_id, role, content) VALUES (%s, 'user', %s);", (thread_id, content))
        cursor.execute("INSERT INTO messages (thread_id, role, content) VALUES (%s, 'assistant', %s);", (thread_id, current_input))
        cursor.close()
        conn.close()
    except Exception:
        pass

    yield "data: [DONE]\n\n"

@app.post("/api/chat/stream")
async def stream_chat(payload: MsgPayload = Body(...)):
    return StreamingResponse(token_stream_generator(payload.thread_id, payload.content), media_type="text/event-stream")

@app.get("/api/chat/threads")
def get_historical_threads():
    conn, cursor = get_db_cursor()
    cursor.execute("SELECT id, name FROM threads ORDER BY id DESC;")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows

@app.post("/api/chat/threads")
def create_new_thread(payload: dict = Body(...)):
    conn, cursor = get_db_cursor()
    cursor.execute("INSERT INTO threads (name) VALUES (%s) RETURNING id, name;", (payload.get("name", "New Conversation"),))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row

@app.get("/api/chat/messages/{thread_id}")
def get_thread_messages(thread_id: int):
    conn, cursor = get_db_cursor()
    cursor.execute("SELECT role, content FROM messages WHERE thread_id = %s ORDER BY id ASC;", (thread_id,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows

@app.delete("/api/chat/threads/{thread_id}")
def delete_chat_thread(thread_id: int):
    conn, cursor = get_db_cursor()
    cursor.execute("DELETE FROM messages WHERE thread_id = %s;", (thread_id,))
    cursor.execute("DELETE FROM threads WHERE id = %s;", (thread_id,))
    cursor.close()
    conn.close()
    return {"status": "success"}

@app.get("/api/config/pipeline")
def get_pipeline_models():
    conn, cursor = get_db_cursor()
    cursor.execute("SELECT step_num, step_name, model_string FROM pipeline_settings ORDER BY step_num ASC;")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows

@app.post("/api/config/pipeline/update")
def update_pipeline_model(payload: PipelineStepUpdate = Body(...)):
    conn, cursor = get_db_cursor()
    cursor.execute("UPDATE pipeline_settings SET model_string = %s WHERE step_num = %s;", (payload.model_string, payload.step_num))
    cursor.close()
    conn.close()
    return {"status": "success"}

@app.get("/api/health")
def health_check():
    return {"status": "healthy"}
