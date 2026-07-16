import os
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from app.database import db

app = FastAPI(title="Canada Family Trip App")

# Secret key required for signing session cookies
app.add_middleware(
    SessionMiddleware, 
    secret_key=os.getenv("SESSION_SECRET_KEY", "super-secret-canada-trip-key")
)

# Mount static files (for your Liquid Glass CSS later)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize Jinja2 templates directory
templates = Jinja2Templates(directory="app/templates")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    if request.session.get("user"):
        return RedirectResponse(url="/dashboard", status_code=303)
    return RedirectResponse(url="/login", status_code=303)

@app.get("/login", response_class=HTMLResponse)
async def login_get(request: Request):
    if request.session.get("user"):
        return RedirectResponse(url="/dashboard", status_code=303)
    
    # Retrieve messages passed through the session, then clear them
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
            # Direct sign up through Supabase Auth
            db.auth.sign_up({"email": email, "password": password})
            request.session["info"] = "Sign up requested! Check your email to confirm your account."
            return RedirectResponse(url="/login", status_code=303)
        else:
            # Direct sign in
            res = db.auth.sign_in_with_password({"email": email, "password": password})
            request.session["user"] = {
                "id": res.user.id,
                "email": res.user.email
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
    user = request.session.get("user")
    if not user:
        request.session["error"] = "Please log in first."
        return RedirectResponse(url="/login", status_code=303)
    
    # Simple verification page (will replace this with full Liquid Glass UI in Phase 3)
    return HTMLResponse(content=f"""
    <html>
        <head>
            <title>Active Session</title>
        </head>
        <body style="background:#090a0f; color:white; font-family:sans-serif; text-align:center; padding-top:10%;">
            <h1 style="color:#a855f7;">Dashboard Connected successfully!</h1>
            <p>Logged in as: <strong>{user['email']}</strong></p>
            <p>User ID: {user['id']}</p>
            <br>
            <a href="/logout" style="color:#818cf8; text-decoration:none; font-weight:bold;">Log Out</a>
        </body>
    </html>
    """)

@app.get("/logout")
async def logout(request: Request):
    try:
        db.auth.sign_out()
    except Exception:
        pass
    request.session.clear()
    request.session["info"] = "Successfully logged out."
    return RedirectResponse(url="/login", status_code=303)
