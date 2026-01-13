# backend/src/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api import routes

app = FastAPI(title="ECHO Backend")

# Configure CORS to allow Streamlit (running on port 8501) to talk to this Backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register the API routes
app.include_router(routes.router)

@app.get("/")
def health_check():
    return {"status": "ok", "message": "ECHO Backend is running"}