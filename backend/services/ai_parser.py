from datetime import datetime
import json

from openai import OpenAI
import pytz

from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL


PARSE_SYSTEM_PROMPT = """你是一个智能秘书助手，专门帮用户解析待办事项。

【任务】
从用户输入中提取：
1. 任务内容（去掉时间词和"提醒"等词，保留核心事项）
2. 分类（从以下选择：工作 / 生活 / 灵感 / 财务 / 学习 / 其他）
3. 提醒时间（转换为 ISO 8601 格式，时区：Asia/Shanghai）
4. 时间是否明确（is_time_clear）

【分类规则】
- 工作：客户、报价、发货、直播、抖音、淘宝、小红书、店铺、供应商、合同、会议
- 财务：房租、账单、还款、工资、打款、收款、税务
- 生活：买菜、看病、取快递、家里、约饭、健身
- 灵感：想法、方案、优化思路、创意
- 学习：看书、学习、课程、培训

【时间解析规则】
- "明天下午" → 明天 15:00
- "明天上午" → 明天 09:00
- "后天" → 后天 09:00
- "月底" → 当月最后一天 09:00
- "周五" / "星期五" → 下个周五 09:00
- "下周" → 下周一 09:00
- 只说"提醒我"但没有时间 → is_time_clear = false
- "过几天" / "最近" / "有空" → is_time_clear = false
- 没有提到时间 → is_time_clear = false

【返回格式】只返回合法 JSON，不要加任何解释或 markdown 代码块
{
  "content": "任务内容",
  "category": "分类",
  "remind_time": "2026-06-03T15:00:00+08:00",
  "is_time_clear": true,
  "original_time_text": "明天下午"
}

如果 is_time_clear 为 false，remind_time 设为 null。
"""


def _fallback(raw_input: str, error: Exception | None = None) -> dict:
    result = {
        "content": raw_input,
        "category": "其他",
        "remind_time": None,
        "is_time_clear": False,
        "original_time_text": None,
        "goal": None,
        "success_criteria": None,
        "related_person": None,
        "missing_fields": ["goal", "success_criteria", "remind_time"],
        "clarify_question": "这件事的目标、完成标准和提醒时间分别是什么？",
        "is_complete": False,
    }
    if error:
        result["parse_error"] = str(error)
    return result


def _strip_json_text(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 2)[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    return cleaned.strip()


def parse_task(raw_input: str, user_timezone: str = "Asia/Shanghai") -> dict:
    if not DEEPSEEK_API_KEY:
        return _fallback(raw_input)

    tz = pytz.timezone(user_timezone)
    now = datetime.now(tz).strftime("%Y-%m-%d %H:%M %A")
    user_prompt = f"【当前时间】{now}\n\n【用户输入】{raw_input}"

    try:
        client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": PARSE_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=300,
        )
        text = response.choices[0].message.content or ""
        return json.loads(_strip_json_text(text))
    except Exception as exc:
        return _fallback(raw_input, exc)
