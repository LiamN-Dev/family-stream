from fastapi import FastAPI
from app.database import db

app = FastAPI(title="Canada Family Trip App")

@app.get("/")
def read_root():
    try:
        # Simple test query to verify Supabase is reachable
        response = db.table("site_settings").select("*").execute()
        return {
            "status": "Online",
            "message": "Connected to Supabase successfully!",
            "settings": response.data
        }
    except Exception as e:
        return {
            "status": "Error",
            "message": "Failed to connect to Supabase.",
            "details": str(e)
        }
