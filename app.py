import os
from flask import Flask, render_template, jsonify, request, session, redirect, url_for
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)

# --- SECURE SESSION KEY ---
app.secret_key = os.environ.get("SESSION_SECRET", "super_secret_jude_key_123!")

# --- DATABASE CONFIG (UPDATE WITH YOUR SESSION POOLER URI) ---
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres.bqzoonqmqicnszdodefn:tJ2*MTXY7vtHtDk@aws-0-us-east-1.pooler.supabase.com:5432/postgres"
)

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, sslmode="require")

# --- AUTO-CREATE TABLES ---
def init_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # 1. Users table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(100) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL,
                role VARCHAR(50) DEFAULT 'vip',
                is_locked BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # 2. Videos table (Modified default to prevent constraint violations)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                id SERIAL PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                youtube_id VARCHAR(50) NOT NULL,
                uploaded_by VARCHAR(100) DEFAULT 'Admin Verified' NOT NULL,
                is_vip_only BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 3. Staff video submissions (Google Drive URLs for Admin review)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS video_submissions (
                id SERIAL PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                drive_url TEXT NOT NULL,
                submitted_by VARCHAR(100) NOT NULL,
                status VARCHAR(50) DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # 4. Comments table
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

        # 5. Global settings (With Google Drive PDF Integration)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS site_settings (
                id INT PRIMARY KEY,
                maintenance_active BOOLEAN DEFAULT FALSE,
                maintenance_message TEXT DEFAULT 'Site is under maintenance.',
                maintenance_timer VARCHAR(100) DEFAULT '',
                banner_active BOOLEAN DEFAULT FALSE,
                banner_text TEXT DEFAULT 'Welcome to our Canada Trip!',
                banner_color VARCHAR(20) DEFAULT '#4f46e5',
                itinerary_pdf_url TEXT DEFAULT '',
                itinerary_last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 6. Targeted popups (Target scopes: global, president, staff, vip, or custom username)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS custom_popups (
                id SERIAL PRIMARY KEY,
                target_user VARCHAR(100) NOT NULL, 
                message TEXT NOT NULL,
                is_read BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 7. Private President Decrees (Direct secure messages from President to Admin)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS presidential_decrees (
                id SERIAL PRIMARY KEY,
                sender VARCHAR(100) DEFAULT 'president',
                message TEXT NOT NULL,
                is_read BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # Insert initial settings row if it doesn't exist
        cur.execute("""
            INSERT INTO site_settings (id, maintenance_active, banner_active, itinerary_pdf_url)
            VALUES (1, FALSE, FALSE, '')
            ON CONFLICT (id) DO NOTHING;
        """)
        
        conn.commit()
        cur.close()
        conn.close()
        print("Database initialized successfully!")
    except Exception as e:
        print(f"Database setup error: {e}")

# --- DEFAULT ACCOUNTS SEED ---
def seed_users():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
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

# --- SECURITY / UTILITY HELPERS ---
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

# --- MIDDLEWARE CHECK FOR MAINTENANCE ---
@app.before_request
def check_maintenance():
    if not request.endpoint or request.endpoint in ['login_page', 'api_login', 'logout', 'static', 'get_settings']:
        return
        
    settings = get_current_settings()
    if settings and settings.get("maintenance_active"):
        if session.get("role") == "admin":
            return
        return render_template("maintenance.html", settings=settings)

# --- HTML ROUTING ---
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

# --- PUBLIC / CORE APIs ---

@app.route("/api/settings")
def get_settings():
    try:
        return jsonify(get_current_settings())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
            return jsonify({"success": False, "error": "Invalid username or password"}), 401
            
        if user["is_locked"]:
            return jsonify({"success": False, "error": "This account is locked. Contact Admin!"}), 403
            
        session["authenticated"] = True
        session["username"] = user["username"]
        session["role"] = user["role"]
        
        return jsonify({"success": True, "role": user["role"]})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# Get videos list (Public vs VIP)
@app.route("/api/videos")
def get_videos():
    role = session.get("role", "guest")
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        if role == "guest":
            cur.execute("SELECT * FROM videos WHERE is_vip_only = FALSE ORDER BY created_at DESC;")
        else:
            cur.execute("SELECT * FROM videos ORDER BY created_at DESC;")
            
        videos = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(videos)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Comment stream system
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
    data = request.json or {}
    video_id = data.get("videoId")
    user_name = session.get("username", "Guest")
    role = session.get("role", "guest")
    text = data.get("text", "").strip()
    
    if not video_id or not text:
        return jsonify({"error": "Bad request parameters"}), 400
        
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            INSERT INTO comments (video_id, user_name, role, text) 
            VALUES (%s, %s, %s, %s) 
            RETURNING *;
        """, (video_id, user_name, role.upper(), text))
        new_comment = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return jsonify(new_comment)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- POPUP ALERTS (TARGETED POPUPS) ---
@app.route("/api/popups")
def get_popups():
    user = session.get("username")
    role = session.get("role", "guest")
    if role == "guest":
        return jsonify([])
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # Checks targets matching user's specific username, their security role, or global
        cur.execute("""
            SELECT * FROM custom_popups 
            WHERE (target_user = %s OR target_user = %s OR target_user = 'global')
            AND is_read = FALSE;
        """, (user, role))
        popups = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(popups)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/popups/read/<int:popup_id>", methods=["POST"])
def read_popup(popup_id):
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

# --- PRESIDENT DECREES (Secure channel to Admin) ---
@app.route("/api/decrees", methods=["GET", "POST"])
def handle_decrees():
    role = session.get("role", "guest")
    if role not in ["president", "admin"]:
        return jsonify({"error": "Unauthorized"}), 401
        
    if request.method == "POST":
        if role != "president":
            return jsonify({"error": "Only the President can launch decrees"}), 403
        data = request.json or {}
        message = data.get("message", "").strip()
        
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("INSERT INTO presidential_decrees (message) VALUES (%s);", (message,))
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
            
    # GET decrees (Both Admin and President can view)
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM presidential_decrees ORDER BY created_at DESC;")
        decrees = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(decrees)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- STAFF SUBMISSIONS ---
@app.route("/api/submissions", methods=["GET", "POST"])
def handle_submissions():
    role = session.get("role", "guest")
    if role == "guest":
        return jsonify({"error": "Unauthorized"}), 401
        
    if request.method == "POST":
        data = request.json or {}
        title = data.get("title")
        drive_url = data.get("driveUrl")
        
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
            
    # GET submissions
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        if role == "admin":
            cur.execute("SELECT * FROM video_submissions ORDER BY created_at DESC;")
        else:
            cur.execute("SELECT * FROM video_submissions WHERE submitted_by = %s ORDER BY created_at DESC;", (session.get("username"),))
        submissions = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(submissions)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- ADMIN SYSTEM-WIDE CONTROLS ---

# User Management (CRUD)
@app.route("/api/admin/users", methods=["GET", "POST"])
def admin_users():
    if session.get("role") != "admin":
        return jsonify({"error": "Admin only"}), 403
        
    if request.method == "POST":
        data = request.json or {}
        username = data.get("username", "").strip()
        password = data.get("password", "").strip()
        role = data.get("role", "vip")
        
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
        cur.execute("SELECT id, username, password, role, is_locked FROM users ORDER BY username ASC;")
        users = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(users)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/admin/users/<int:user_id>", methods=["PUT", "DELETE"])
def edit_user(user_id):
    if session.get("role") != "admin":
        return jsonify({"error": "Admin only"}), 403
        
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

# Settings management
@app.route("/api/admin/settings", methods=["POST"])
def update_settings():
    if session.get("role") != "admin":
        return jsonify({"error": "Admin only"}), 403
        
    data = request.json or {}
    
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("SELECT itinerary_pdf_url FROM site_settings WHERE id = 1;")
        row = cur.fetchone()
        old_pdf = row["itinerary_pdf_url"] if row else ""
        new_pdf = data.get("itinerary_pdf_url", old_pdf)
        
        if new_pdf != old_pdf:
            cur.execute("""
                UPDATE site_settings 
                SET maintenance_active = %s, maintenance_message = %s, maintenance_timer = %s,
                    banner_active = %s, banner_text = %s, banner_color = %s, 
                    itinerary_pdf_url = %s, itinerary_last_updated = CURRENT_TIMESTAMP
                WHERE id = 1;
            """, (
                data.get("maintenance_active"), data.get("maintenance_message"), data.get("maintenance_timer"),
                data.get("banner_active"), data.get("banner_text"), data.get("banner_color"), new_pdf
            ))
        else:
            cur.execute("""
                UPDATE site_settings 
                SET maintenance_active = %s, maintenance_message = %s, maintenance_timer = %s,
                    banner_active = %s, banner_text = %s, banner_color = %s
                WHERE id = 1;
            """, (
                data.get("maintenance_active"), data.get("maintenance_message"), data.get("maintenance_timer"),
                data.get("banner_active"), data.get("banner_text"), data.get("banner_color")
            ))
            
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Broadcast target popups
@app.route("/api/admin/popup", methods=["POST"])
def make_popup():
    if session.get("role") != "admin":
        return jsonify({"error": "Admin only"}), 403
    data = request.json or {}
    target = data.get("target") # Can be 'global', 'president', 'staff', 'vip', or a username
    message = data.get("message")
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO custom_popups (target_user, message) VALUES (%s, %s);", (target, message))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Publish verified Youtube Video
@app.route("/api/admin/publish-video", methods=["POST"])
def publish_video():
    if session.get("role") != "admin":
        return jsonify({"error": "Admin only"}), 403
    data = request.json or {}
    title = data.get("title")
    youtube_url = data.get("youtubeUrl")
    is_vip = data.get("isVip", False)
    submission_id = data.get("submissionId")
    
    # Secure YT parser
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
        # Safe uploaded_by designation included directly in query parameters
        cur.execute("""
            INSERT INTO videos (title, youtube_id, uploaded_by, is_vip_only)
            VALUES (%s, %s, 'Admin Verified', %s);
        """, (title, yt_id, is_vip))
        
        if submission_id:
            cur.execute("UPDATE video_submissions SET status = 'approved' WHERE id = %s;", (submission_id,))
            
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/admin/submissions/reject/<int:sub_id>", methods=["POST"])
def reject_submission(sub_id):
    if session.get("role") != "admin":
        return jsonify({"error": "Admin only"}), 403
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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
