import os
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional, List
from supabase import create_client, Client

# ==========================================
# 1. FAILSAFE: AUTO-CREATE REQUIRED DIRECTORIES
# ==========================================
os.makedirs("static", exist_ok=True)
os.makedirs("templates", exist_ok=True)

# Initialize FastAPI
app = FastAPI(title="Canadian Rockies Family Portal")

# Allow CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Connect to Supabase
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Missing SUPABASE_URL or SUPABASE_KEY environment variables.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==========================================
# 2. PYDANTIC SCHEMAS (DATA MODELS)
# ==========================================
class LoginRequest(BaseModel):
    username: str
    password: str

class UserCreate(BaseModel):
    username: str
    password: str
    role: str

class UserUpdate(BaseModel):
    id: int
    username: str
    password: str
    role: str
    is_locked: bool

class VideoUpload(BaseModel):
    title: str
    url: str
    category: str  # 'general', 'vip'
    uploaded_by: str
    is_approved: bool = True

class SendMessageRequest(BaseModel):
    sender_id: int
    sender_username: str
    recipient_id: Optional[int] = None
    recipient_role: Optional[str] = None
    message_text: str
    is_red_flag: bool = False

class UpdateItineraryRequest(BaseModel):
    pdf_url: str

class BannerSettings(BaseModel):
    active: bool
    text: str
    color: str

class MaintenanceSettings(BaseModel):
    active: bool
    message: str
    timer: Optional[str] = None

# ==========================================
# 3. ROUTE LOGIC
# ==========================================

# Simple Status Endpoint
@app.get("/api/health")
def health_check():
    return {"status": "online", "supabase_connected": True}

# Login Endpoint
@app.post("/api/login")
def login(data: LoginRequest):
    user_query = supabase.table("users").select("*").eq("username", data.username).execute()
    if not user_query.data:
        raise HTTPException(status_code=401, detail="User not found")
    
    user = user_query.data[0]
    if user["is_locked"]:
        raise HTTPException(status_code=403, detail="This account has been locked by the admin.")
    
    if user["password"] != data.password:
        raise HTTPException(status_code=401, detail="Invalid password")
    
    return {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"]
    }

# Video Management (GET and POST)
@app.get("/api/videos")
def get_videos(category: Optional[str] = None):
    query = supabase.table("videos").select("*")
    if category:
        query = query.eq("category", category)
    response = query.order("created_at", desc=True).execute()
    return response.data

@app.post("/api/videos")
def add_video(video: VideoUpload):
    response = supabase.table("videos").insert(video.model_dump()).execute()
    return {"status": "success", "video": response.data}

@app.post("/api/videos/approve/{video_id}")
def approve_video(video_id: int):
    response = supabase.table("videos").update({"is_approved": True}).eq("id", video_id).execute()
    return {"status": "success", "video": response.data}

@app.delete("/api/videos/{video_id}")
def delete_video(video_id: int):
    supabase.table("videos").delete().eq("id", video_id).execute()
    return {"status": "success"}

# Chat Messaging
@app.get("/api/messages")
def get_messages(user_id: int, role: str):
    # Fetch global chat, and directed chats (sent by or targeting this user/role)
    response = supabase.table("messages").select("*").order("created_at", desc=False).execute()
    # Basic filtering logic on client or db side. Let's return the messages:
    return response.data

@app.post("/api/messages")
def send_message(msg: SendMessageRequest):
    response = supabase.table("messages").insert(msg.model_dump()).execute()
    return {"status": "success", "message": response.data}

# Itinerary
@app.get("/api/itinerary")
def get_itinerary():
    response = supabase.table("itinerary").select("*").order("id", desc=True).limit(1).execute()
    if response.data:
        return response.data[0]
    return {"pdf_url": "", "last_updated": "never"}

@app.post("/api/itinerary")
def update_itinerary(data: UpdateItineraryRequest):
    # Insert a new itinerary entry or update existing
    response = supabase.table("itinerary").insert({"pdf_url": data.pdf_url}).execute()
    return {"status": "success", "itinerary": response.data}

# Admin Site Settings (Banner / Maintenance)
@app.get("/api/settings")
def get_settings():
    response = supabase.table("site_settings").select("*").execute()
    settings_dict = {item["key"]: item["value"] for item in response.data}
    return settings_dict

@app.post("/api/settings/banner")
def update_banner(banner: BannerSettings):
    response = supabase.table("site_settings").update({"value": banner.model_dump()}).eq("key", "banner").execute()
    return {"status": "success", "banner": response.data}

@app.post("/api/settings/maintenance")
def update_maintenance(maint: MaintenanceSettings):
    response = supabase.table("site_settings").update({"value": maint.model_dump()}).eq("key", "maintenance").execute()
    return {"status": "success", "maintenance": response.data}

# Admin User Controller
@app.get("/api/admin/users")
def get_all_users():
    response = supabase.table("users").select("*").order("id", desc=False).execute()
    return response.data

@app.post("/api/admin/users")
def create_user(user: UserCreate):
    response = supabase.table("users").insert(user.model_dump()).execute()
    return {"status": "success", "user": response.data}

@app.put("/api/admin/users")
def update_user(user: UserUpdate):
    response = supabase.table("users").update({
        "username": user.username,
        "password": user.password,
        "role": user.role,
        "is_locked": user.is_locked
    }).eq("id", user.id).execute()
    return {"status": "success", "user": response.data}

@app.delete("/api/admin/users/{user_id}")
def delete_user(user_id: int):
    supabase.table("users").delete().eq("id", user_id).execute()
    return {"status": "success"}

# Serve the Frontend directly
@app.get("/", response_class=HTMLResponse)
def get_home():
    # If index.html is in templates directory
    filepath = os.path.join("templates", "index.html")
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            return HTMLResponse(content=f.read(), status_code=200)
    return HTMLResponse(content="<h1>Server is Running. Place your index.html in the 'templates' folder!</h1>", status_code=200)

# Mount static files safely (even if empty, folder is guaranteed to exist now)
app.mount("/static", StaticFiles(directory="static"), name="static")
