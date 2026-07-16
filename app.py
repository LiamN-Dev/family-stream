import os
from flask import Flask, render_template, jsonify, request, session, redirect, url_for
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)

# --- SECURE SESSION KEY ---
app.secret_key = os.environ.get("SESSION_SECRET", "super_secret_rockies_key_2026!")

# --- DATABASE CONFIG (UPDATE WITH YOUR SESSION POOLER URI) ---
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres.bqzoonqmqicnszdodefn:YOUR_ACTUAL_PASSWORD_HERE@aws-0-us-east-1.pooler.supabase.com:5432/postgres"
)

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, sslmode="require")

# --- INITIALIZE DATABASE SCHEMA ---
def init_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # 1. Drop old tables to prevent schema clashes
        cur.execute("DROP TABLE IF EXISTS messages CASCADE;")
        cur.execute("DROP TABLE IF EXISTS video_submissions CASCADE;")
        cur.execute("DROP TABLE IF EXISTS video_requests CASCADE;")
        cur.execute("DROP TABLE IF EXISTS custom_popups CASCADE;")
        cur.execute("DROP TABLE IF EXISTS videos CASCADE;")
        cur.execute("DROP TABLE IF EXISTS users CASCADE;")
        cur.execute("DROP TABLE IF EXISTS site_settings CASCADE;")
        
        # 2. Users Table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(100) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL,
                role VARCHAR(50) DEFAULT 'vip' NOT NULL, -- admin, president, staff, vip
                is_locked BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # 3. Videos Table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                id SERIAL PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                youtube_id VARCHAR(100) NOT NULL,
                uploaded_by VARCHAR(100) DEFAULT 'Admin Verified' NOT NULL,
                category VARCHAR(50) DEFAULT 'general' NOT NULL, -- general, vip
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 4. Worker Link Submissions (Google Drive URL Queue for Admin review)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS video_submissions (
                id SERIAL PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                drive_url TEXT NOT NULL,
                submitted_by VARCHAR(100) NOT NULL,
                status VARCHAR(50) DEFAULT 'pending' NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 5. VIP Video Request Box
        cur.execute("""
            CREATE TABLE IF NOT EXISTS video_requests (
                id SERIAL PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                details TEXT NOT NULL,
                requested_by VARCHAR(100) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # 6. Secure Message Routing Ledger (Chats)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                sender VARCHAR(100) NOT NULL,
                recipient VARCHAR(100) NOT NULL, -- 'admin', 'president', 'staff_global', or specific username
                message TEXT NOT NULL,
                is_red_flagged BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 7. Targeted Popups Alerts
        cur.execute("""
            CREATE TABLE IF NOT EXISTS custom_popups (
                id SERIAL PRIMARY KEY,
                target_scope VARCHAR(100) NOT NULL, -- 'all', 'vip', 'staff', 'president', or specific username
                message TEXT NOT NULL,
                is_read BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 8. Global Settings & Active Banner Settings
        cur.execute("""
            CREATE TABLE IF NOT EXISTS site_settings (
                id INT PRIMARY KEY,
                maintenance_active BOOLEAN DEFAULT FALSE,
                maintenance_message TEXT DEFAULT 'Site is under maintenance.',
                maintenance_timer VARCHAR(100) DEFAULT '',
                banner_active BOOLEAN DEFAULT FALSE,
                banner_text TEXT DEFAULT 'Welcome to our Canada Trip!',
                banner_color VARCHAR(20) DEFAULT '#059669',
                itinerary_pdf_url TEXT DEFAULT '',
                itinerary_version INT DEFAULT 1,
                itinerary_last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # Default Seed Row
        cur.execute("""
            INSERT INTO site_settings (id, maintenance_active, banner_active, itinerary_pdf_url, itinerary_version)
            VALUES (1, FALSE, FALSE, '', 1)
            ON CONFLICT (id) DO NOTHING;
        """)
        
        conn.commit()
        cur.close()
        conn.close()
        print("Database initialized successfully with persistent schemas!")
    except Exception as e:
        print(f"Database setup error: {e}")

# --- SYSTEM SEED ACCOUNTS ---
def seed_users():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # Initial core setup credentials
        cur.execute("""
            INSERT INTO users (username, password, role, is_locked)
            VALUES 
            ('admin', 'admin123', 'admin', FALSE),
            ('president', 'pres123', 'president', FALSE),
            ('staff', 'staff123', 'staff', FALSE),
            ('vip', 'vip123', 'vip', FALSE)
            ON CONFLICT (username) DO NOTHING;
        """)
        conn.commit()
        cur.close()
        conn.close()
        print("Database seeded with default accounts!")
    except Exception as e:
        print(f"Error seeding database: {e}")

init_db()
seed_users()

# --- UTILITIES ---
def get_current_settings():
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM site_settings WHERE id = 1;")
        settings = cur.fetchone()
        cur.close()
        conn.close()
        return settings
    except Exception as e:
        print(f"Error getting settings: {e}")
        return None

# --- MAINTENANCE CHECK ---
@app.before_request
def check_maintenance():
    if not request.endpoint or request.endpoint in ['login_page', 'api_login', 'logout', 'static', 'get_settings']:
        return
        
    settings = get_current_settings()
    if settings and settings.get("maintenance_active"):
        if session.get("role") == "admin":
            return
        return render_template("maintenance.html", settings=settings)

# --- WEB PAGE ROUTES ---
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/login")
def login_page():
    if session.get("authenticated"):
        return redirect(url_for("home"))
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

# --- PUBLIC APIS ---

@app.route("/api/settings")
def get_settings():
    return jsonify(get_current_settings())

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.json or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM users WHERE username = %s;", (username,))
        user = cur.fetchone()
        cur.close()
        conn.close()
        
        if not user or user["password"] != password:
            return jsonify({"success": False, "error": "Invalid credentials"}), 401
            
        if user["is_locked"]:
            return jsonify({"success": False, "error": "Account is locked. Please contact Admin!"}), 403
            
        session["authenticated"] = True
        session["username"] = user["username"]
        session["role"] = user["role"]
        
        return jsonify({"success": True, "role": user["role"]})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# Get both general and VIP videos matching authentication status
@app.route("/api/videos")
def get_videos():
    role = session.get("role", "guest")
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        if role == "guest":
            # Guest can see only General category videos
            cur.execute("SELECT * FROM videos WHERE category = 'general' ORDER BY created_at DESC;")
        else:
            # Authenticated users get to filter both catalogs
            cur.execute("SELECT * FROM videos ORDER BY created_at DESC;")
            
        videos = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(videos)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- VIP EXCLUSIVE REQUESTS ---
@app.route("/api/vip/requests", methods=["GET", "POST"])
def handle_video_requests():
    role = session.get("role", "guest")
    if role not in ["vip", "admin"]:
        return jsonify({"error": "Unauthorized Access"}), 403
        
    if request.method == "POST":
        data = request.json or {}
        title = data.get("title", "").strip()
        details = data.get("details", "").strip()
        
        if not title or not details:
            return jsonify({"error": "Missing title or details"}), 400
            
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO video_requests (title, details, requested_by)
                VALUES (%s, %s, %s);
            """, (title, details, session.get("username")))
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # GET requests (Vips see theirs, Admin sees all)
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        if role == "admin":
            cur.execute("SELECT * FROM video_requests ORDER BY created_at DESC;")
        else:
            cur.execute("SELECT * FROM video_requests WHERE requested_by = %s ORDER BY created_at DESC;", (session.get("username"),))
        reqs = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(reqs)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- WORKER STAFF SUBMISSIONS ---
@app.route("/api/submissions", methods=["GET", "POST"])
def handle_video_submissions():
    role = session.get("role", "guest")
    if role not in ["staff", "president", "admin"]:
        return jsonify({"error": "Unauthorized Access"}), 403
        
    if request.method == "POST":
        data = request.json or {}
        title = data.get("title", "").strip()
        drive_url = data.get("drive_url", "").strip()
        
        if not title or not drive_url:
            return jsonify({"error": "Missing video parameters"}), 400
            
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO video_submissions (title, drive_url, submitted_by)
                VALUES (%s, %s, %s);
            """, (title, drive_url, session.get("username")))
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # GET submissions queue
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        if role == "admin":
            cur.execute("SELECT * FROM video_submissions ORDER BY created_at DESC;")
        else:
            cur.execute("SELECT * FROM video_submissions WHERE submitted_by = %s ORDER BY created_at DESC;", (session.get("username"),))
        subs = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(subs)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- CHAT & COMMUNICATOR CHANNELS ---
@app.route("/api/messages", methods=["GET", "POST"])
def handle_messages():
    username = session.get("username")
    role = session.get("role", "guest")
    if role == "guest":
        return jsonify({"error": "Access Denied"}), 401
        
    if request.method == "POST":
        data = request.json or {}
        recipient = data.get("recipient", "").strip()
        msg_text = data.get("message", "").strip()
        
        if not recipient or not msg_text:
            return jsonify({"error": "Bad payload parameters"}), 400
            
        is_red = (role == "president" and recipient == "admin")
            
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO messages (sender, recipient, message, is_red_flagged)
                VALUES (%s, %s, %s, %s);
            """, (username, recipient, msg_text, is_red))
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # GET available chat rooms
    target = request.args.get("room", "staff_global") # staff_global, admin, president, or specific user
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        if target == "staff_global":
            # Visible to staff, president, admin
            cur.execute("SELECT * FROM messages WHERE recipient = 'staff_global' ORDER BY created_at ASC;")
        else:
            # Handles private DMs between two accounts
            cur.execute("""
                SELECT * FROM messages 
                WHERE (sender = %s AND recipient = %s)
                OR (sender = %s AND recipient = %s)
                ORDER BY created_at ASC;
            """, (username, target, target, username))
            
        messages = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(messages)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- POPUP ALERTS POLLING SYSTEM ---
@app.route("/api/popups")
def get_pending_popups():
    username = session.get("username")
    role = session.get("role", "guest")
    if role == "guest":
        return jsonify([])
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT * FROM custom_popups
            WHERE (target_scope = 'all' OR target_scope = %s OR target_scope = %s)
            AND is_read = FALSE
            ORDER BY created_at ASC;
        """, (role, username))
        popups = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(popups)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/popups/read/<int:popup_id>", methods=["POST"])
def mark_popup_read(popup_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE custom_popups SET is_read = TRUE WHERE id = %s;", (popup_id,))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- ADMIN POWER-CONTROLLER MODULES ---

# 1. Full Dynamic User Management (CRUD)
@app.route("/api/admin/users", methods=["GET", "POST"])
def admin_users_control():
    if session.get("role") != "admin":
        return jsonify({"error": "Access Denied"}), 403
        
    if request.method == "POST":
        data = request.json or {}
        username = data.get("username", "").strip()
        password = data.get("password", "").strip()
        role = data.get("role", "vip").strip()
        
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO users (username, password, role)
                VALUES (%s, %s, %s);
            """, (username, password, role))
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
            
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id, username, password, role, is_locked FROM users ORDER BY id ASC;")
        users = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(users)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/admin/users/<int:user_id>", methods=["PUT", "DELETE"])
def edit_system_user(user_id):
    if session.get("role") != "admin":
        return jsonify({"error": "Access Denied"}), 403
        
    if request.method == "DELETE":
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("DELETE FROM users WHERE id = %s;", (user_id,))
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
            
    data = request.json or {}
    username = data.get("username")
    password = data.get("password")
    role = data.get("role")
    is_locked = data.get("is_locked")
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE users 
            SET username = %s, password = %s, role = %s, is_locked = %s 
            WHERE id = %s;
        """, (username, password, role, is_locked, user_id))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# 2. Daily Itinerary & Settings Engine (Increments version counter)
@app.route("/api/admin/settings", methods=["POST"])
def update_settings():
    if session.get("role") != "admin":
        return jsonify({"error": "Access Denied"}), 403
        
    data = request.json or {}
    
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Read old config state to look for changes in itinerary URL
        cur.execute("SELECT itinerary_pdf_url, itinerary_version FROM site_settings WHERE id = 1;")
        row = cur.fetchone()
        old_pdf = row["itinerary_pdf_url"] if row else ""
        old_version = row["itinerary_version"] if row else 1
        
        new_pdf = data.get("itinerary_pdf_url", old_pdf).strip()
        new_version = old_version
        
        # If the admin changed the daily schedule PDF, increment the tracking version
        if new_pdf != old_pdf:
            new_version += 1
            
        cur.execute("""
            UPDATE site_settings 
            SET maintenance_active = %s, maintenance_message = %s, maintenance_timer = %s,
                banner_active = %s, banner_text = %s, banner_color = %s, 
                itinerary_pdf_url = %s, itinerary_version = %s, itinerary_last_updated = CURRENT_TIMESTAMP
            WHERE id = 1;
        """, (
            data.get("maintenance_active"), data.get("maintenance_message"), data.get("maintenance_timer"),
            data.get("banner_active"), data.get("banner_text"), data.get("banner_color"), 
            new_pdf, new_version
        ))
            
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# 3. Queue Dispatcher (Custom Popups Broadcasts)
@app.route("/api/admin/popup", methods=["POST"])
def broadcast_custom_alert():
    if session.get("role") != "admin":
        return jsonify({"error": "Access Denied"}), 403
    data = request.json or {}
    target_scope = data.get("target_scope", "all").strip() # 'all', 'vip', 'staff', 'president' or explicit username
    message = data.get("message", "").strip()
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO custom_popups (target_scope, message) 
            VALUES (%s, %s);
        """, (target_scope, message))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# 4. Verified Video Publisher (Post directly from dashboard or submission review)
@app.route("/api/admin/publish-video", methods=["POST"])
def publish_verified_video():
    if session.get("role") != "admin":
        return jsonify({"error": "Access Denied"}), 403
    data = request.json or {}
    title = data.get("title", "").strip()
    youtube_url = data.get("youtube_url", "").strip()
    category = data.get("category", "general").strip() # general, vip
    submission_id = data.get("submission_id")
    
    # Simple YouTube ID Parser for multiple URL variations
    yt_id = ""
    if "v=" in youtube_url:
        yt_id = youtube_url.split("v=")[1].split("&")[0]
    elif "youtu.be/" in youtube_url:
        yt_id = youtube_url.split("youtu.be/")[1].split("?")[0]
    else:
        yt_id = youtube_url
        
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO videos (title, youtube_id, uploaded_by, category)
            VALUES (%s, %s, 'Admin Verified', %s);
        """, (title, yt_id, category))
        
        if submission_id:
            cur.execute("UPDATE video_submissions SET status = 'approved' WHERE id = %s;", (submission_id,))
            
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/admin/submissions/reject/<int:sub_id>", methods=["POST"])
def reject_queue_submission(sub_id):
    if session.get("role") != "admin":
        return jsonify({"error": "Access Denied"}), 403
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE video_submissions SET status = 'rejected' WHERE id = %s;", (sub_id,))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- INCOMING SYSTEM CHAT AUDIT (Used by Admin to review Presidential DMs) ---
@app.route("/api/admin/chat-audit")
def fetch_all_system_chats():
    if session.get("role") != "admin":
        return jsonify([])
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # Pulls all database messages for admin dashboard overview
        cur.execute("SELECT * FROM messages ORDER BY created_at DESC;")
        msgs = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(msgs)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
