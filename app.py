import os
from flask import Flask, render_template, jsonify, request, session, redirect, url_for
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)

# --- SESSION KEY ---
# Set SESSION_SECRET as a real environment variable on Render.
# This fallback only gets used if that env var is missing.
app.secret_key = os.environ.get("SESSION_SECRET", "super_secret_jude_key_123!")
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# --- DATABASE CONFIG ---
# Paste your real Supabase password between "postgres:" and "@db..." below,
# OR (recommended) set DATABASE_URL as an environment variable on Render instead.
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:PASTE_YOUR_PASSWORD_HERE@db.bqzoonqmqicnszdodefn.supabase.co:6543/postgres"
)

WORKER_ROLES = ("staff", "president", "admin")  # accounts that can use Messenger


def get_db_connection():
    return psycopg2.connect(DATABASE_URL, sslmode="require")


# --- SCHEMA SETUP (safe to run on every boot — never drops or overwrites data) ---
def init_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()

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
        # Personalization fields — added separately so upgrading an existing
        # database never touches rows that already exist.
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS display_name VARCHAR(100);")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS favorite_color VARCHAR(20);")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                id SERIAL PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                youtube_id VARCHAR(50) NOT NULL,
                is_vip_only BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

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

        cur.execute("""
            CREATE TABLE IF NOT EXISTS site_settings (
                id INT PRIMARY KEY,
                maintenance_active BOOLEAN DEFAULT FALSE,
                maintenance_message TEXT DEFAULT 'Site is under maintenance. Back online soon!',
                maintenance_timer VARCHAR(100) DEFAULT '',
                banner_active BOOLEAN DEFAULT FALSE,
                banner_text TEXT DEFAULT 'Welcome to our Canada Trip!',
                banner_color VARCHAR(20) DEFAULT '#4f46e5',
                itinerary_pdf_url TEXT DEFAULT '',
                itinerary_last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                id SERIAL PRIMARY KEY,
                sender VARCHAR(100) NOT NULL,
                receiver VARCHAR(100) NOT NULL,  -- 'global_staff' or an exact username
                message TEXT NOT NULL,
                is_flagged_red BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS custom_popups (
                id SERIAL PRIMARY KEY,
                target_user VARCHAR(100) NOT NULL,  -- exact username, 'all_staff', or 'president'
                message TEXT NOT NULL,
                is_read BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS video_requests (
                id SERIAL PRIMARY KEY,
                requested_by VARCHAR(100) NOT NULL,
                request_text TEXT NOT NULL,
                status VARCHAR(50) DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

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


def seed_users():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO users (username, password, role, display_name, favorite_color, is_locked)
            VALUES
            ('admin', 'admin123', 'admin', 'Admin', '#2bb1a3', FALSE),
            ('president', 'pres123', 'president', 'President', '#c23b4a', FALSE),
            ('staff', 'staff123', 'staff', 'Staff', '#c1652f', FALSE),
            ('vip', 'vip123', 'vip', 'VIP', '#d7a441', FALSE)
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


# --- HELPERS ---
def get_current_settings():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM site_settings WHERE id = 1;")
    settings = cur.fetchone()
    cur.close()
    conn.close()
    return settings


def require_role(*roles):
    return session.get("role") in roles


def parse_youtube_id(url):
    url = (url or "").strip()
    if "v=" in url:
        return url.split("v=")[1].split("&")[0]
    if "youtu.be/" in url:
        return url.split("youtu.be/")[1].split("?")[0]
    return url


# --- MAINTENANCE MIDDLEWARE ---
@app.before_request
def check_maintenance():
    allowed_endpoints = ['login_page', 'api_login', 'logout', 'static', 'get_settings']
    if request.endpoint in allowed_endpoints:
        return
    try:
        settings = get_current_settings()
    except Exception as e:
        print(f"Maintenance check failed, DB unreachable: {e}")
        return
    if settings and settings.get("maintenance_active"):
        if session.get("role") == "admin":
            return
        return render_template("maintenance.html", settings=settings)


# --- HTML ROUTES ---
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


# --- AUTH ---
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

        session.permanent = True
        session["authenticated"] = True
        session["username"] = user["username"]
        session["role"] = user["role"]
        session["display_name"] = user.get("display_name") or user["username"]
        session["favorite_color"] = user.get("favorite_color") or ""

        return jsonify({"success": True, "role": user["role"]})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --- SITE SETTINGS (maintenance / banner / itinerary) ---
@app.route("/api/settings")
def get_settings():
    try:
        return jsonify(get_current_settings())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/settings", methods=["POST"])
def update_settings():
    if not require_role("admin"):
        return jsonify({"error": "Admin only"}), 403

    data = request.json or {}
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("SELECT itinerary_pdf_url FROM site_settings WHERE id = 1;")
        old_pdf = cur.fetchone()["itinerary_pdf_url"]
        new_pdf = data.get("itinerary_pdf_url", old_pdf)

        if new_pdf != old_pdf:
            cur.execute("""
                UPDATE site_settings
                SET maintenance_active = %s, maintenance_message = %s, maintenance_timer = %s,
                    banner_active = %s, banner_text = %s, banner_color = %s,
                    itinerary_pdf_url = %s, itinerary_last_updated = CURRENT_TIMESTAMP
                WHERE id = 1;
            """, (
                bool(data.get("maintenance_active")), data.get("maintenance_message", ""), data.get("maintenance_timer", ""),
                bool(data.get("banner_active")), data.get("banner_text", ""), data.get("banner_color", "#4f46e5"), new_pdf
            ))
        else:
            cur.execute("""
                UPDATE site_settings
                SET maintenance_active = %s, maintenance_message = %s, maintenance_timer = %s,
                    banner_active = %s, banner_text = %s, banner_color = %s
                WHERE id = 1;
            """, (
                bool(data.get("maintenance_active")), data.get("maintenance_message", ""), data.get("maintenance_timer", ""),
                bool(data.get("banner_active")), data.get("banner_text", ""), data.get("banner_color", "#4f46e5")
            ))

        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- VIDEOS ---
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


@app.route("/api/admin/videos", methods=["POST"])
def add_video():
    if not require_role("admin"):
        return jsonify({"error": "Admin only"}), 403
    data = request.json or {}
    title = (data.get("title") or "").strip()
    yt_id = parse_youtube_id(data.get("youtubeUrl"))
    is_vip = bool(data.get("isVip", False))

    if not title or not yt_id:
        return jsonify({"error": "Title and YouTube URL are required"}), 400

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO videos (title, youtube_id, is_vip_only)
            VALUES (%s, %s, %s);
        """, (title, yt_id, is_vip))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- COMMENTS ---
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
    user_name = session.get("display_name") or session.get("username", "Guest")
    role = session.get("role", "guest")
    text = (data.get("text") or "").strip()

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


# --- VIP VIDEO REQUESTS ---
@app.route("/api/video-requests", methods=["GET", "POST"])
def video_requests():
    role = session.get("role", "guest")

    if request.method == "POST":
        if role != "vip":
            return jsonify({"error": "VIP only"}), 403
        data = request.json or {}
        text = (data.get("text") or "").strip()
        if not text:
            return jsonify({"error": "Please describe the video you'd like made"}), 400
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO video_requests (requested_by, request_text)
                VALUES (%s, %s);
            """, (session.get("username"), text))
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # GET: admin sees everything, a VIP sees only their own requests
    if role not in ("admin", "vip"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        if role == "admin":
            cur.execute("SELECT * FROM video_requests ORDER BY created_at DESC;")
        else:
            cur.execute("SELECT * FROM video_requests WHERE requested_by = %s ORDER BY created_at DESC;", (session.get("username"),))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(rows)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/video-requests/<int:req_id>", methods=["POST"])
def update_video_request(req_id):
    if not require_role("admin"):
        return jsonify({"error": "Admin only"}), 403
    data = request.json or {}
    status = data.get("status", "fulfilled")
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


# --- MESSENGER (staff / president / admin) ---
@app.route("/api/directory")
def directory():
    if session.get("role") not in WORKER_ROLES:
        return jsonify({"error": "Unauthorized"}), 401
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT username, role, display_name FROM users
            WHERE role IN ('staff', 'president', 'admin') AND username != %s
            ORDER BY role, username;
        """, (session.get("username"),))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(rows)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/chat", methods=["GET", "POST"])
def handle_chats():
    current_user = session.get("username")
    role = session.get("role", "guest")
    if role not in WORKER_ROLES:
        return jsonify({"error": "Login required"}), 401

    if request.method == "POST":
        data = request.json or {}
        receiver = (data.get("receiver") or "").strip()
        message = (data.get("message") or "").strip()
        if not receiver or not message:
            return jsonify({"error": "Message cannot be empty"}), 400

        try:
            conn = get_db_connection()
            cur = conn.cursor(cursor_factory=RealDictCursor)

            is_flagged = False
            if receiver != "global_staff":
                cur.execute("SELECT role FROM users WHERE username = %s;", (receiver,))
                target = cur.fetchone()
                if target and role == "president" and target["role"] == "admin":
                    is_flagged = True

            cur.execute("""
                INSERT INTO chats (sender, receiver, message, is_flagged_red)
                VALUES (%s, %s, %s, %s);
            """, (current_user, receiver, message, is_flagged))
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT * FROM chats
            WHERE receiver = 'global_staff' OR receiver = %s OR sender = %s
            ORDER BY created_at ASC;
        """, (current_user, current_user))
        messages = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(messages)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- POPUP ALERTS ---
@app.route("/api/popups")
def get_popups():
    user = session.get("username")
    role = session.get("role", "guest")
    if role == "guest":
        return jsonify([])
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT * FROM custom_popups
            WHERE is_read = FALSE
              AND (
                target_user = %s
                OR (target_user = 'all_staff' AND %s IN ('staff', 'president'))
                OR (target_user = 'president' AND %s = 'president')
              )
            ORDER BY created_at ASC;
        """, (user, role, role))
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


@app.route("/api/admin/popup", methods=["POST"])
def make_popup():
    if not require_role("admin"):
        return jsonify({"error": "Admin only"}), 403
    data = request.json or {}
    target = (data.get("target") or "").strip()
    message = (data.get("message") or "").strip()
    if not target or not message:
        return jsonify({"error": "Target and message are required"}), 400

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


# --- ADMIN: USER MANAGEMENT ---
@app.route("/api/admin/users", methods=["GET", "POST"])
def admin_users():
    if not require_role("admin"):
        return jsonify({"error": "Admin only"}), 403

    if request.method == "POST":
        data = request.json or {}
        username = (data.get("username") or "").strip()
        password = (data.get("password") or "").strip()
        role = data.get("role", "vip")
        display_name = (data.get("display_name") or username).strip()
        favorite_color = data.get("favorite_color") or "#47a68c"

        if not username or not password:
            return jsonify({"error": "Username and password are required"}), 400

        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO users (username, password, role, display_name, favorite_color)
                VALUES (%s, %s, %s, %s, %s);
            """, (username, password, role, display_name, favorite_color))
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT id, username, password, role, is_locked, display_name, favorite_color
            FROM users ORDER BY username ASC;
        """)
        users = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(users)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/users/<int:user_id>", methods=["PUT", "DELETE"])
def edit_user(user_id):
    if not require_role("admin"):
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
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE users
            SET username = %s, password = %s, role = %s, is_locked = %s,
                display_name = %s, favorite_color = %s
            WHERE id = %s;
        """, (
            data.get("username"), data.get("password"), data.get("role"), data.get("is_locked"),
            data.get("display_name"), data.get("favorite_color"), user_id
        ))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
