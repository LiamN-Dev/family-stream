import os
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from app.database import db

app = FastAPI(title="Canada Family Trip App")

# Secure session cookies tracking logins and roles
app.add_middleware(
    SessionMiddleware, 
    secret_key=os.getenv("SESSION_SECRET_KEY", "super-secret-canada-trip-key")
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize page templates
templates = Jinja2Templates(directory="app/templates")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    # Automatically drop guests onto the dashboard
    return RedirectResponse(url="/dashboard", status_code=303)

@app.get("/login", response_class=HTMLResponse)
async def login_get(request: Request):
    if request.session.get("user"):
        return RedirectResponse(url="/dashboard", status_code=303)
    
    error = request.session.pop("error", None)
    info = request.session.pop("info", None)
    
    return templates.TemplateResponse(
        "login.html", 
        {"request": request, "error": error, "info": info}
    )

@app.post("/login")
async def login_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    action: str = Form(...)
):
    try:
        if action == "signup":
            # Create the account in Supabase Auth
            db.auth.sign_up({"email": email, "password": password})
            request.session["info"] = "Account request submitted! Check your email to verify."
            return RedirectResponse(url="/login", status_code=303)
        else:
            # Authenticate credentials
            res = db.auth.sign_in_with_password({"email": email, "password": password})
            
            # Retrieve the user's assigned role from the custom profiles table
            profile_res = db.table("profiles").select("role, username").eq("id", res.user.id).execute()
            role = "general"
            username = email.split("@")[0]
            
            if profile_res.data:
                role = profile_res.data[0].get("role", "general")
                username = profile_res.data[0].get("username", username)
            
            # Store everything inside secure session cookies
            request.session["user"] = {
                "id": res.user.id,
                "email": res.user.email,
                "username": username,
                "role": role
            }
            return RedirectResponse(url="/dashboard", status_code=303)
    except Exception as e:
        err_msg = str(e)
        if "invalid login credentials" in err_msg.lower():
            err_msg = "Invalid email or password."
        request.session["error"] = err_msg
        return RedirectResponse(url="/login", status_code=303)

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    # Extract user or default to an unauthenticated "General" guest
    user = request.session.get("user")
    role = user.get("role", "general") if user else "general"
    username = user.get("username", "Guest") if user else "Guest"
    
    # 1. Fetch Global Settings (Maintenance state and Banner layout)
    try:
        settings_res = db.table("site_settings").select("*").eq("id", 1).execute()
        settings = settings_res.data[0] if settings_res.data else {
            "is_maintenance": False,
            "maintenance_message": "Under maintenance.",
            "banner_enabled": False,
            "banner_text": "",
            "banner_color": "#4A90E2"
        }
    except Exception:
        settings = {
            "is_maintenance": False,
            "maintenance_message": "Database disconnected. Under construction.",
            "banner_enabled": False,
            "banner_text": "",
            "banner_color": "#4A90E2"
        }

    # Lock non-admins out of the entire site if maintenance mode is enabled
    if settings.get("is_maintenance") and role != "admin":
        return HTMLResponse(content=f"""
        <html>
            <head>
                <title>Site Offline</title>
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;700&display=swap" rel="stylesheet">
                <style>
                    body {{
                        font-family: 'Plus Jakarta Sans', sans-serif;
                        background: #090a0f;
                        color: white;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        height: 100vh;
                        margin: 0;
                        padding: 20px;
                        box-sizing: border-box;
                    }}
                    .maintenance-box {{
                        background: rgba(255, 255, 255, 0.03);
                        border: 1px solid rgba(255, 255, 255, 0.08);
                        backdrop-filter: blur(20px);
                        padding: 40px;
                        border-radius: 24px;
                        max-width: 500px;
                        text-align: center;
                        box-shadow: 0 20px 50px rgba(0,0,0,0.5);
                    }}
                    h1 {{ color: #a855f7; margin-top: 0; font-size: 2rem; }}
                    p {{ color: #9ca3af; line-height: 1.6; font-size: 1.1rem; }}
                </style>
            </head>
            <body>
                <div class="maintenance-box">
                    <h1>Maintenance Mode Active</h1>
                    <p>{settings.get("maintenance_message")}</p>
                </div>
            </body>
        </html>
        """, status_code=503)

    # 2. Fetch Approved Videos (General users only get General. VIPs and above get everything)
    try:
        query = db.table("videos").select("*")
        if role == "general":
            query = query.eq("category", "general")
        videos_res = query.order("created_at", desc=True).execute()
        videos = videos_res.data
    except Exception:
        videos = []

    # 3. Fetch current Itinerary documents
    try:
        itinerary_res = db.table("itinerary").select("*").order("id", desc=False).execute()
        itinerary_items = itinerary_res.data
    except Exception:
        itinerary_items = []

    # Get the global itinerary system version ID (defaults to 1 if none is configured yet)
    current_itinerary_version = 1
    if itinerary_items:
        # Determine current version based on the latest update parameter
        current_itinerary_version = max([item.get("version_id", 1) for item in itinerary_items])

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "role": role,
            "username": username,
            "settings": settings,
            "videos": videos,
            "itinerary_items": itinerary_items,
            "current_itinerary_version": current_itinerary_version
        }
    )

@app.get("/logout")
async def logout(request: Request):
    try:
        db.auth.sign_out()
    except Exception:
        pass
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
