from pathlib import Path
from dotenv import load_dotenv
import os

dotenv_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
FROM_EMAIL = os.getenv("FROM_EMAIL")
SECRET_KEY = os.getenv("SECRET_KEY")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
WECOM_WEBHOOK_URL = os.getenv("WECOM_WEBHOOK_URL")
WECOM_PHONE_MAP_JSON = os.getenv("WECOM_PHONE_MAP_JSON", "{}")
