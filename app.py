import os
from flask import Flask, render_template, jsonify, request
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)

# --- DATABASE CONFIG ---
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:YOUR_ACTUAL_PASSWORD@db.bqzoonqmqicnszdodefn.supabase.co:6543/postgres"
)

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, sslmode="require")

# --- AUTO-CREATE TABLES ---
def init_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # 1. Videos table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                id SERIAL PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                youtube_id VARCHAR(50) NOT NULL,
                uploaded_by VARCHAR(100) NOT NULL,
                is_vip_only INT DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # 2. Comments table
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
        
        conn.commit()
        cur.close()
        conn.close()
        print("Successfully connected to Supabase & verified tables exist!")
    except Exception as e:
        print(f"Error initializing Supabase database: {e}")

init_db()

# --- ROUTES ---
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/login")
def login():
    return render_template("login.html")

# --- API ENDPOINTS ---
@app.route("/api/videos")
def get_videos():
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM videos ORDER BY created_at DESC;")
        videos = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(videos)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/comments/<int:video_id>")
def get_comments(video_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM comments WHERE video_id = %s ORDER BY created_at DESC;", (video_id,))
        comments = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(comments)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
