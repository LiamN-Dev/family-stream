import sys
from supabase import create_client, Client
from app.config import SUPABASE_URL, SUPABASE_KEY

if not SUPABASE_URL or not SUPABASE_KEY:
    print("\n[FATAL] Database connection credentials are missing!")
    print("Please ensure SUPABASE_URL and SUPABASE_KEY are set up in your Render Environment settings.\n")
    sys.exit(1)

try:
    # Initialize the synchronized Supabase Client
    db: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("🚀 Supabase database client initialized successfully!")
except Exception as e:
    print("\n--- [SUPABASE CONNECTION FAILURE] ---")
    print(f"Failed to initialize Supabase client. Error details:\n{str(e)}")
    print("\n👉 Troubleshooting Steps:")
    print("1. Go to your Render Dashboard -> your Web Service -> Environment tab.")
    print("2. Verify that 'SUPABASE_KEY' does not have trailing spaces, newline breaks, or wrapping quotes.")
    print("3. Ensure you are using the service_role key or anon key from your Supabase API settings.")
    print("--------------------------------------\n")
    raise e
