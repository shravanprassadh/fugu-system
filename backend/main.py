import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from core.database import run_query, initialize_infra

app = FastAPI(title="Sovereign API Engine")

# Security rule allowing your future Vercel frontend to securely talk to this API
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
        print(f"Database initialization mapping failed: {str(e)}")

@app.get("/api/health")
def health_check():
    return {"status": "online", "engine": "FastAPI Layer"}

@app.get("/api/threads")
def get_all_threads():
    try:
        # Pulls the active conversation history track lists directly from SQL
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
        return {"status": "success", "message": "Thread created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
