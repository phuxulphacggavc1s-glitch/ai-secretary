"""
运行方式：把这个文件放到 D:\项目\AI_Secretary\backend\ 目录下
然后在命令行运行：python test_connection.py
"""
import os
import sys

# 加载 .env 文件
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception as e:
    print("dotenv 加载失败:", e)

print("=" * 40)
print("1. 检查环境变量")
print("=" * 40)

supabase_url = os.getenv("SUPABASE_URL", "")
service_key = os.getenv("SUPABASE_SERVICE_KEY", "")
deepseek_key = os.getenv("DEEPSEEK_API_KEY", "")
secret_key = os.getenv("SECRET_KEY", "")

print("SUPABASE_URL:", supabase_url[:40] if supabase_url else "❌ 未设置")
print("SUPABASE_SERVICE_KEY:", service_key[:20] + "..." if service_key else "❌ 未设置")
print("DEEPSEEK_API_KEY:", deepseek_key[:15] + "..." if deepseek_key else "❌ 未设置")
print("SECRET_KEY:", "✅ 已设置" if secret_key and "随便填" not in secret_key else "❌ 还是占位符，需要改成真实随机字符串")

print()
print("=" * 40)
print("2. 测试 Supabase 连接")
print("=" * 40)

try:
    from supabase import create_client
    sb = create_client(supabase_url, service_key)
    result = sb.table("tasks").select("id").limit(1).execute()
    print("✅ Supabase 连接成功")
except Exception as e:
    print("❌ Supabase 失败:", str(e)[:150])

print()
print("=" * 40)
print("3. 测试 DeepSeek AI 连接")
print("=" * 40)

try:
    from openai import OpenAI
    deepseek_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    client = OpenAI(api_key=deepseek_key, base_url=deepseek_url)
    resp = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": "回复两个字：测试成功"}],
        max_tokens=10
    )
    print("✅ DeepSeek 连接成功:", resp.choices[0].message.content)
except Exception as e:
    print("❌ DeepSeek 失败:", str(e)[:150])

print()
print("=" * 40)
print("完成")
print("=" * 40)
