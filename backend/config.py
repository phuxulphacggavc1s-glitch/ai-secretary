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

# 企业微信自建应用（双向对话）
WECOM_CORP_ID = os.getenv("WECOM_CORP_ID")
WECOM_APP_SECRET = os.getenv("WECOM_APP_SECRET")
WECOM_APP_AGENT_ID = os.getenv("WECOM_APP_AGENT_ID")
WECOM_APP_TOKEN = os.getenv("WECOM_APP_TOKEN")
WECOM_APP_AES_KEY = os.getenv("WECOM_APP_AES_KEY")
# 企业微信成员账号 -> 应用内用户ID 的映射，如 {"YiXu": "supabase-user-uuid"}
WECOM_APP_USER_MAP = os.getenv("WECOM_APP_USER_MAP", "{}")
