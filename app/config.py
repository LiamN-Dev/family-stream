import os
from dotenv import load_dotenv

# Load local .env file if running in development
load_dotenv()

def clean_env_var(value: str) -> str:
    """Safely strips whitespace and bounding quotes from environment variables."""
    if not value:
        return ""
    value = value.strip()
    # Strip accidental wrapping double or single quotes
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        value = value[1:-1]
    return value.strip()

# Safely extract and sanitize keys
SUPABASE_URL = clean_env_var(os.getenv("SUPABASE_URL", ""))

# Try a few common fallback names in case of typos on Render
SUPABASE_KEY = clean_env_var(
    os.getenv("SUPABASE_KEY") or 
    os.getenv("SUPABASE_ANON_KEY") or 
    os.getenv("SUPABASE_SERVICE_ROLE_KEY") or 
    ""
)

# Render Diagnostic Logs (Completely safe; never prints the actual secret key)
print("--- [DATABASE CONFIG DIAGNOSTICS] ---")
if not SUPABASE_URL:
    print("❌ ERROR: SUPABASE_URL is completely missing or empty!")
else:
    print(f"✅ SUPABASE_URL detected (Length: {len(SUPABASE_URL)}) -> Starts with: {SUPABASE_URL[:12]}...")

if not SUPABASE_KEY:
    print("❌ ERROR: SUPABASE_KEY is completely missing or empty!")
else:
    # Supabase keys are JWTs, typically starting with 'ey'
    is_jwt = SUPABASE_KEY.startswith("ey")
    print(f"✅ SUPABASE_KEY detected (Length: {len(SUPABASE_KEY)})")
    print(f"   - Starts with 'ey' (Standard JWT format): {is_jwt}")
    print(f"   - First 5 characters: '{SUPABASE_KEY[:5]}'")
    print(f"   - Last 5 characters: '{SUPABASE_KEY[-5:]}'")
print("--------------------------------------")
