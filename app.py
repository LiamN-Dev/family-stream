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
    "postgresql://postgres.bqzoonqmqicnszdodefn:tJ2*MTXY7vtHtDk@aws-0-us-east-1.pooler.supabase.com:5432/postgres"
)

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, sslmode="require")

# --- INITIALIZE DATABASE SCHEMA ---
def init_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # 1. Drop old tables to prevent schema clashes
        cur.execute("DROP TABLE IF EXISTS comments CASCADE;")
        cur.execute("DROP TABLE IF EXISTS messages CASCADE;")
        cur.execute("DROP TABLE IF EXISTS video_submissions CASCADE;")
        cur.execute("DROP TABLE IF EXISTS video_requests CASCADE;")
        cur.execute("DROP TABLE IF EXISTS custom_popups CASCADE;")
        cur.execute("DROP TABLE IF EXISTS videos CASCADE;")
        cur.execute("DROP TABLE IF EXISTS users CASCADE;")
        cur.execute("DROP TABLE IF EXISTS site_settings CASCADE;")
        
        # 2. Users Table (Added display_name & favorite_color)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(100) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL,
                display_name VARCHAR(100),
                favorite_color VARCHAR(20) DEFAULT '#47a68c',
                role VARCHAR(50) DEFAULT 'vip' NOT NULL,
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
                category VARCHAR(50) DEFAULT 'general' NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 4. Comments Table (Newly mapped to frontend requests)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS comments (
                id SERIAL PRIMARY KEY,
                video_id INT NOT NULL,
                user_name VARCHAR(100) NOT NULL,
                role VARCHAR(50) NOT NULL,
                text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 5. Worker Link Submissions
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

        # 6. VIP Video Request Box
        cur.execute("""
            CREATE TABLE IF NOT EXISTS video_requests (
                id SERIAL PRIMARY KEY,
                title VARCHAR(255),
                request_text TEXT NOT NULL,
                requested_by VARCHAR(100) NOT NULL,
                status VARCHAR(50) DEFAULT 'pending' NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # 7. Secure Message Routing Ledger
        cur.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                sender VARCHAR(100) NOT NULL,
                receiver VARCHAR(100) NOT NULL,
                message TEXT NOT NULL,
                is_flagged_red BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 8. Targeted Popups Alerts
        cur.execute("""
            CREATE TABLE IF NOT EXISTS custom_popups (
                id SERIAL PRIMARY KEY,
                target_scope VARCHAR(100) NOT NULL,
                message TEXT NOT NULL,
                is_read BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 9. Global Settings
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
        cur.execute("""
            INSERT INTO users (username, password, display_name, favorite_color, role, is_locked)
            VALUES 
            ('admin', 'admin123', 'Admin', '#2bb1a3', 'admin', FALSE),
            ('president', 'pres123', 'President', '#c23b4a', 'president', FALSE),
            ('staff', 'staff123', 'Staff Worker', '#c1652f', 'staff', FALSE),
            ('vip', 'vip123', 'VIP Guest', '#d7a441', 'vip', FALSE)
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
        session["display_name"] = user["display_name"]
        
        return jsonify({"success": True, "role": user["role"]})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/videos")
def get_videos():
    role = session.get("role", "guest")
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        if role == "guest":
            cur.execute("SELECT * FROM videos WHERE category = 'general' ORDER BY created_at DESC;")
        else:
            cur.execute("SELECT * FROM videos ORDER BY created_at DESC;")
            
        videos = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(videos)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- COMMENTS API ---
@app.route("/api/comments/<int:video_id>")
def get_comments(video_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM comments WHERE video_id = %s ORDER BY created_at ASC;", (video_id,))
        comments = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(comments)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/comments", methods=["POST"])
def post_comment():
    if not session.get("authenticated"):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.json or {}
    video_id = data.get("videoId")
    text = data.get("text", "").strip()
    if not video_id or not text:
        return jsonify({"error": "Missing parameters"}), 400
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO comments (video_id, user_name, role, text)
            VALUES (%s, %s, %s, %s);
        """, (video_id, session.get("display_name") or session.get("username"), session.get("role"), text))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- VIP EXCLUSIVE REQUESTS ---
@app.route("/api/video-requests", methods=["GET", "POST"])
def handle_video_requests():
    role = session.get("role", "guest")
    if role not in ["vip", "admin"]:
        return jsonify({"error": "Unauthorized Access"}), 403
        
    if request.method == "POST":
        data = request.json or {}
        text = data.get("text", "").strip()
        title = data.get("title", "Video Request")
        
        if not text:
            return jsonify({"error": "Missing details"}), 400
            
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO video_requests (title, request_text, requested_by)
                VALUES (%s, %s, %s);
            """, (title, text, session.get("username")))
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

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

@app.route("/api/admin/video-requests/<int:req_id>", methods=["POST"])
def admin_video_request_status(req_id):
    if session.get("role") != "admin":
        return jsonify({"error": "Unauthorized"}), 403
    data = request.json or {}
    status = data.get("status", "pending")
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE video_requests SET status = %s WHERE id = %s;", (status, req_id))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- DIRECTORY & CHAT ---
@app.route("/api/directory")
def get_directory():
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT username, display_name, role FROM users ORDER BY username ASC;")
        users = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(users)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/chat", methods=["GET", "POST"])
def handle_messages():
    username = session.get("username")
    role = session.get("role", "guest")
    if role == "guest":
        return jsonify({"error": "Access Denied"}), 401
        
    if request.method == "POST":
        data = request.json or {}
        receiver = data.get("receiver", "").strip()
        msg_text = data.get("message", "").strip()
        
        if not receiver or not msg_text:
            return jsonify({"error": "Bad payload parameters"}), 400
            
        is_red = (role == "president" and receiver == "admin")
            
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO messages (sender, receiver, message, is_flagged_red)
                VALUES (%s, %s, %s, %s);
            """, (username, receiver, msg_text, is_red))
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM messages ORDER BY created_at ASC;")
        messages = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(messages)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- POPUP ALERTS ---
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

# --- ADMIN USER CRUD ---
@app.route("/api/admin/users", methods=["GET", "POST"])
def admin_users_control():
    if session.get("role") != "admin":
        return jsonify({"error": "Access Denied"}), 403
        
    if request.method == "POST":
        data = request.json or {}
        username = data.get("username", "").strip()
        password = data.get("password", "").strip()
        display_name = data.get("display_name", "").strip()
        favorite_color = data.get("favorite_color", "#47a68c").strip()
        role = data.get("role", "vip").strip()
        
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO users (username, password, display_name, favorite_color, role)
                VALUES (%s, %s, %s, %s, %s);
            """, (username, password, display_name, favorite_color, role))
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
            
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id, username, password, display_name, favorite_color, role, is_locked FROM users ORDER BY id ASC;")
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
    display_name = data.get("display_name")
    favorite_color = data.get("favorite_color")
    role = data.get("role")
    is_locked = data.get("is_locked")
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE users 
            SET username = %s, password = %s, display_name = %s, favorite_color = %s, role = %s, is_locked = %s 
            WHERE id = %s;
        """, (username, password, display_name, favorite_color, role, is_locked, user_id))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- ADMIN SYSTEM SETTINGS ---
@app.route("/api/admin/settings", methods=["POST"])
def update_settings():
    if session.get("role") != "admin":
        return jsonify({"error": "Access Denied"}), 403
        
    data = request.json or {}
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("SELECT itinerary_pdf_url, itinerary_version FROM site_settings WHERE id = 1;")
        row = cur.fetchone()
        old_pdf = row["itinerary_pdf_url"] if row else ""
        old_version = row["itinerary_version"] if row else 1
        
        new_pdf = data.get("itinerary_pdf_url", old_pdf).strip()
        new_version = old_version
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

@app.route("/api/admin/popup", methods=["POST"])
def broadcast_custom_alert():
    if session.get("role") != "admin":
        return jsonify({"error": "Access Denied"}), 403
    data = request.json or {}
    target_scope = data.get("target", "all").strip()
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

@app.route("/api/admin/videos", methods=["POST"])
def publish_verified_video():
    if session.get("role") != "admin":
        return jsonify({"error": "Access Denied"}), 403
    data = request.json or {}
    title = data.get("title", "").strip()
    youtube_url = data.get("youtubeUrl", "").strip()
    is_vip = data.get("isVip", False)
    category = "vip" if is_vip else "general"
    
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
        
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
