"""
AI Personal Assistant — Standalone Telegram Bot v2.0
Personality Profile System + Gemini Pro Weekly Analysis + Sage Mode
"""

import json
import os
import random
import logging
from datetime import datetime, timedelta

import google.generativeai as genai
import gspread
from google.oauth2.service_account import Credentials
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from zoneinfo import ZoneInfo

import config

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============================================================
# GOOGLE SHEETS MANAGER
# ============================================================
class SheetsManager:
    def __init__(self):
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = Credentials.from_service_account_file(
            config.SHEETS_CREDENTIALS_FILE, scopes=scopes
        )
        self.client = gspread.authorize(creds)
        self.spreadsheet = self.client.open_by_key(config.SPREADSHEET_ID)
        logger.info("Google Sheets connection established.")

    def get_sheet(self, name):
        return self.spreadsheet.worksheet(name)

    def get_all_rows(self, sheet_name):
        try:
            sheet = self.get_sheet(sheet_name)
            return sheet.get_all_records()
        except Exception as e:
            logger.error(f"Sheets read error ({sheet_name}): {e}")
            return []

    def append_row(self, sheet_name, row_dict):
        try:
            sheet = self.get_sheet(sheet_name)
            headers = sheet.row_values(1)
            row = [row_dict.get(h, "") for h in headers]
            sheet.append_row(row, value_input_option="USER_ENTERED")
            return True
        except Exception as e:
            logger.error(f"Sheets write error ({sheet_name}): {e}")
            return False

    def get_recent_rows(self, sheet_name, n=10):
        rows = self.get_all_rows(sheet_name)
        return rows[-n:] if len(rows) > n else rows

# ============================================================
# MEMORY MANAGER
# ============================================================
class MemoryManager:
    def __init__(self):
        self.file = config.MEMORY_FILE
        self.data = self._load()

    def _load(self):
        if os.path.exists(self.file):
            with open(self.file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save(self):
        with open(self.file, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def get_history(self, agent_name):
        return self.data.get(agent_name, [])

    def add_message(self, agent_name, role, content):
        if agent_name not in self.data:
            self.data[agent_name] = []
        self.data[agent_name].append({"role": role, "content": content})
        if len(self.data[agent_name]) > config.MEMORY_WINDOW * 2:
            self.data[agent_name] = self.data[agent_name][-config.MEMORY_WINDOW * 2:]
        self._save()

# ============================================================
# PERSONALITY PROFILE MANAGER
# ============================================================
class ProfileManager:
    """Big Five + values + communication style profile"""

    def __init__(self):
        self.profile_file = config.PROFILE_FILE
        self.qa_file = config.PROFILE_QA_FILE
        self.profile = self._load(self.profile_file, self._default_profile())
        self.qa_history = self._load(self.qa_file, {"questions": [], "asked_indices": []})

    def _default_profile(self):
        return {
            "big_five": {
                "openness": 0.5,
                "conscientiousness": 0.5,
                "extraversion": 0.5,
                "agreeableness": 0.5,
                "neuroticism": 0.5
            },
            "communication_style": "friendly and concise",
            "motivation_style": "balanced - sometimes strict, sometimes supportive",
            "humor_style": "unknown",
            "values": [],
            "personality_summary": "Not enough data collected yet.",
            "last_updated": None,
            "total_answers": 0
        }

    def _load(self, filepath, default):
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        return default

    def _save(self):
        with open(self.profile_file, "w", encoding="utf-8") as f:
            json.dump(self.profile, f, ensure_ascii=False, indent=2)
        with open(self.qa_file, "w", encoding="utf-8") as f:
            json.dump(self.qa_history, f, ensure_ascii=False, indent=2)

    def record_answer(self, question, answer):
        self.qa_history["questions"].append({
            "q": question,
            "a": answer,
            "date": datetime.now(ZoneInfo(config.TIMEZONE)).strftime("%Y-%m-%d %H:%M")
        })
        self.profile["total_answers"] = len(self.qa_history["questions"])
        self._save()

    def get_profile_summary(self):
        return self.profile.get("personality_summary", "Analysis not performed yet.")

    def get_profile_for_prompt(self):
        if self.profile["total_answers"] < 3:
            return "User personality profile not established yet."
        p = self.profile
        bf = p["big_five"]
        return f"""USER PERSONALITY PROFILE:
- Openness: {bf['openness']:.1f}/1.0
- Conscientiousness: {bf['conscientiousness']:.1f}/1.0
- Extraversion: {bf['extraversion']:.1f}/1.0
- Agreeableness: {bf['agreeableness']:.1f}/1.0
- Neuroticism: {bf['neuroticism']:.1f}/1.0
- Communication Preference: {p['communication_style']}
- Motivation Style: {p['motivation_style']}
- Humor Style: {p['humor_style']}
- Values: {', '.join(p['values']) if p['values'] else 'Not determined'}
- Summary: {p['personality_summary']}

ADAPT YOUR COMMUNICATION STYLE TO THIS PROFILE. Use the tone the user prefers."""

    async def analyze_profile(self, gemini_pro):
        if len(self.qa_history["questions"]) < 5:
            return
        qa_text = json.dumps(self.qa_history["questions"][-30:], ensure_ascii=False)
        prompt = f"""You are an expert in personality psychology. Analyze the following Q&A history and extract a profile based on the Big Five personality model.

Q&A HISTORY:
{qa_text}

RETURN A JSON WITH THIS EXACT FORMAT (do not write anything else):
{{
  "big_five": {{
    "openness": float between 0.0-1.0,
    "conscientiousness": float between 0.0-1.0,
    "extraversion": float between 0.0-1.0,
    "agreeableness": float between 0.0-1.0,
    "neuroticism": float between 0.0-1.0
  }},
  "communication_style": "user's preferred communication style",
  "motivation_style": "best motivation method for the user",
  "humor_style": "user's sense of humor",
  "values": ["value1", "value2", "value3"],
  "personality_summary": "2-3 sentence personality summary"
}}"""
        try:
            response = gemini_pro.chat_pro(prompt, "Perform personality analysis")
            text = response.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]
            result = json.loads(text)
            self.profile.update(result)
            self.profile["last_updated"] = datetime.now(ZoneInfo(config.TIMEZONE)).strftime("%Y-%m-%d %H:%M")
            self._save()
            logger.info("Personality profile updated!")
        except Exception as e:
            logger.error(f"Profile analysis error: {e}")

# ============================================================
# GEMINI AI MANAGER
# ============================================================
class GeminiManager:
    def __init__(self):
        genai.configure(api_key=config.GEMINI_API_KEY)
        self.model = genai.GenerativeModel(config.GEMINI_MODEL)
        self.model_pro = genai.GenerativeModel(config.GEMINI_MODEL_PRO)
        logger.info("Gemini API connection established (Flash + Pro).")

    def chat(self, system_prompt, user_message, history=None):
        try:
            messages = []
            if history:
                for msg in history[-config.MEMORY_WINDOW:]:
                    messages.append({"role": msg["role"], "parts": [msg["content"]]})
            chat = self.model.start_chat(history=messages)
            full_prompt = f"[SYSTEM INSTRUCTION]\n{system_prompt}\n\n[USER MESSAGE]\n{user_message}"
            response = chat.send_message(full_prompt)
            return response.text
        except Exception as e:
            logger.error(f"Gemini Flash error: {e}")
            return f"An error occurred: {str(e)}"

    def chat_pro(self, system_prompt, user_message):
        try:
            chat = self.model_pro.start_chat()
            full_prompt = f"[SYSTEM INSTRUCTION]\n{system_prompt}\n\n[USER MESSAGE]\n{user_message}"
            response = chat.send_message(full_prompt)
            return response.text
        except Exception as e:
            logger.error(f"Gemini Pro error: {e}")
            return f"An error occurred: {str(e)}"

# ============================================================
# UTILITIES
# ============================================================
def now_local():
    return datetime.now(ZoneInfo(config.TIMEZONE))

# ============================================================
# AGENTS
# ============================================================
class ReportAgent:
    @staticmethod
    def handle(payload, sheets, gemini, memory, profile_mgr):
        data = sheets.get_recent_rows(config.SHEET_GUN_VERI, 15)
        now = now_local().strftime("%Y-%m-%d %H:%M")
        profile_ctx = profile_mgr.get_profile_for_prompt()
        prompt = f"""You are a Performance Report Agent.

{profile_ctx}

TASK:
1. Future statements (I will do, planning to) -> Save as PLAN.
2. Past statements (I did, completed) -> Save as ACTUAL.
3. Review the existing data and provide a contextual response.

CURRENT DAILY DATA:
{json.dumps(data, ensure_ascii=False)}

Date/Time: {now}"""

        history = memory.get_history("report")
        response = gemini.chat(prompt, payload, history)
        memory.add_message("report", "user", payload)
        memory.add_message("report", "model", response)

        # Always save unless it's just a read request
        if any(k in payload.lower() for k in ["show", "list", "read", "what did i do", "report"]):
            pass  # Only reading, don't save
        else:
            report_type = "PLAN" if any(k in payload.lower() for k in ["will do", "plan", "goal", "work on"]) else "ACTUAL"
            saved = sheets.append_row(config.SHEET_GUN_VERI, {
                "Date": now_local().strftime("%Y-%m-%d"),
                "Time": now_local().strftime("%H:%M"),
                "Report": f"{report_type}: {payload}"
            })
            if saved and response:
                response += "\n\n✅ Saved successfully!"
        return response


class TodoAgent:
    @staticmethod
    def handle(payload, sheets, gemini, memory, profile_mgr):
        data = sheets.get_all_rows(config.SHEET_TODO)
        now = now_local().strftime("%Y-%m-%d %H:%M")
        profile_ctx = profile_mgr.get_profile_for_prompt()
        prompt = f"""You are a To-Do List Management Agent.

{profile_ctx}

TASK:
1. New task -> Save it. 
2. Completed -> Update status. 
3. Show -> List tasks.
Extract category if provided (e.g., Work, Study, Project).

CURRENT TASKS:
{json.dumps(data, ensure_ascii=False)}

Date/Time: {now}"""

        history = memory.get_history("todo")
        response = gemini.chat(prompt, payload, history)
        memory.add_message("todo", "user", payload)
        memory.add_message("todo", "model", response)

        if not any(k in payload.lower() for k in ["list", "show", "what is there", "my tasks"]):
            category, activity = "", payload
            if ":" in payload:
                parts = payload.split(":", 1)
                category, activity = parts[0].strip(), parts[1].strip()
            saved = sheets.append_row(config.SHEET_TODO, {
                "Date": now_local().strftime("%Y-%m-%d"),
                "Category": category, "Task": activity, "Status": "Pending"
            })
            if saved and response:
                response += "\n\n✅ Task added!"
            elif saved:
                response = "✅ Task added!"
        return response


class DiaryAgent:
    @staticmethod
    def handle(payload, sheets, gemini, memory, profile_mgr):
        data = sheets.get_recent_rows(config.SHEET_GUNLUK, 15)
        now = now_local().strftime("%Y-%m-%d %H:%M")
        profile_ctx = profile_mgr.get_profile_for_prompt()
        prompt = f"""You are a Diary Agent.

{profile_ctx}

TASK: Record events or memories. If asked about the past, read and respond.

CURRENT DIARY:
{json.dumps(data, ensure_ascii=False)}

Date/Time: {now}"""

        history = memory.get_history("diary")
        response = gemini.chat(prompt, payload, history)
        memory.add_message("diary", "user", payload)
        memory.add_message("diary", "model", response)

        if not any(k in payload.lower() for k in ["show", "read", "what did i do", "past"]):
            saved = sheets.append_row(config.SHEET_GUNLUK, {
                "Date": now_local().strftime("%Y-%m-%d"), "Entry": payload
            })
            if saved and response:
                response += "\n\n✅ Saved to diary!"
            elif saved:
                response = "✅ Saved to diary!"
        return response


class ProjectAgent:
    @staticmethod
    def handle(payload, sheets, gemini, memory, profile_mgr):
        data = sheets.get_all_rows(config.SHEET_PROJELER)
        now = now_local().strftime("%Y-%m-%d %H:%M")
        profile_ctx = profile_mgr.get_profile_for_prompt()
        prompt = f"""You are a Project Management Agent.

{profile_ctx}

TASK: Add new project/subtask, check status, or update progress.
Columns: Project, Subtask, Status, Percentage, Deadline, Notes

CURRENT PROJECTS:
{json.dumps(data, ensure_ascii=False)}

Date/Time: {now}"""

        history = memory.get_history("project")
        response = gemini.chat(prompt, payload, history)
        memory.add_message("project", "user", payload)
        memory.add_message("project", "model", response)
        return response


class ChatAgent:
    @staticmethod
    def handle(payload, gemini, memory, profile_mgr):
        now = now_local().strftime("%Y-%m-%d %H:%M")
        profile_ctx = profile_mgr.get_profile_for_prompt()
        prompt = f"""You are a friendly and engaging chat assistant.

{profile_ctx}

Date/Time: {now}"""

        history = memory.get_history("chat")
        response = gemini.chat(prompt, payload, history)
        memory.add_message("chat", "user", payload)
        memory.add_message("chat", "model", response)
        return response


class SageAgent:
    @staticmethod
    def handle(payload, gemini, memory, profile_mgr):
        now = now_local().strftime("%Y-%m-%d %H:%M")
        profile_ctx = profile_mgr.get_profile_for_prompt()
        prompt = f"""You are a legendary 'Sage' with a profound worldview and a highly analytical mind. The user is consulting you about real-life challenges or dilemmas.

{profile_ctx}

TASKS AND RULES:
1. SECRETLY take the user's personality profile, strengths/weaknesses, and values (provided above) into account to show them the most logical, efficient, and correct path.
2. NEVER reveal to the user that you know their personality profile (DO NOT use phrases like "because of your high agreeableness" or "according to your profile"). Only use this information in the subtext of your advice and guidance.
3. Offer a perspective that is philosophical yet completely pragmatic, actionable, and mind-opening.
4. Do not be overly long or boring; be clear and impactful.

Date/Time: {now}"""

        history = memory.get_history("sage")
        response = gemini.chat(prompt, payload, history)
        memory.add_message("sage", "user", payload)
        memory.add_message("sage", "model", response)
        
        # Record this conversation to feed the personality analysis
        profile_mgr.record_answer("User consulted the Sage regarding:", payload)
        
        return response

# ============================================================
# HELP MENU
# ============================================================
HELP_TEXT = """🤖 **Personal Assistant v2.0**

/r [message] - Read/Write to the Report table
/t [task] - Manage To-Do list
/g [memory] - Read/Write to the Diary
/p [project] - Project tracking
/bilge [topic] - Consult the Sage for mind-opening advice
/profil - Show your Personality Profile
/h - Show this menu

_(Messages without a command go to standard chat)_"""

# ============================================================
# TELEGRAM HANDLERS
# ============================================================
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")

async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payload = " ".join(context.args) if context.args else "Show my latest reports"
    await update.message.reply_chat_action("typing")
    response = ReportAgent.handle(payload, context.bot_data["sheets"],
                                  context.bot_data["gemini"], context.bot_data["memory"],
                                  context.bot_data["profile"])
    await update.message.reply_text(response)

async def cmd_todo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payload = " ".join(context.args) if context.args else "List my tasks"
    await update.message.reply_chat_action("typing")
    response = TodoAgent.handle(payload, context.bot_data["sheets"],
                                 context.bot_data["gemini"], context.bot_data["memory"],
                                 context.bot_data["profile"])
    await update.message.reply_text(response)

async def cmd_diary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payload = " ".join(context.args) if context.args else "Show my latest diary entries"
    await update.message.reply_chat_action("typing")
    response = DiaryAgent.handle(payload, context.bot_data["sheets"],
                                    context.bot_data["gemini"], context.bot_data["memory"],
                                    context.bot_data["profile"])
    await update.message.reply_text(response)

async def cmd_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payload = " ".join(context.args) if context.args else "Show project statuses"
    await update.message.reply_chat_action("typing")
    response = ProjectAgent.handle(payload, context.bot_data["sheets"],
                                   context.bot_data["gemini"], context.bot_data["memory"],
                                   context.bot_data["profile"])
    await update.message.reply_text(response)

async def cmd_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show personality profile"""
    profile_mgr = context.bot_data["profile"]
    p = profile_mgr.profile
    bf = p["big_five"]

    text = f"""🧠 **Your Personality Profile**

📊 **Big Five Scores:**
• Openness: {'█' * int(bf['openness']*10)}{'░' * (10-int(bf['openness']*10))} {bf['openness']:.1f}
• Conscientiousness: {'█' * int(bf['conscientiousness']*10)}{'░' * (10-int(bf['conscientiousness']*10))} {bf['conscientiousness']:.1f}
• Extraversion: {'█' * int(bf['extraversion']*10)}{'░' * (10-int(bf['extraversion']*10))} {bf['extraversion']:.1f}
• Agreeableness: {'█' * int(bf['agreeableness']*10)}{'░' * (10-int(bf['agreeableness']*10))} {bf['agreeableness']:.1f}
• Neuroticism: {'█' * int(bf['neuroticism']*10)}{'░' * (10-int(bf['neuroticism']*10))} {bf['neuroticism']:.1f}

💬 Communication: {p['communication_style']}
🎯 Motivation: {p['motivation_style']}
😄 Humor: {p['humor_style']}
💎 Values: {', '.join(p['values']) if p['values'] else 'Not determined yet'}

📝 {p['personality_summary']}

_Total {p['total_answers']} questions answered. Last updated: {p.get('last_updated', 'Not yet')}_"""

    await update.message.reply_text(text)

async def cmd_sage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Please write the topic you want to consult about. Example: /bilge What path should I follow in my career?")
        return

    payload = " ".join(context.args)
    await update.message.reply_chat_action("typing")
    
    response = SageAgent.handle(payload, context.bot_data["gemini"],
                                 context.bot_data["memory"], context.bot_data["profile"])
    await update.message.reply_text(response)
    
    # If this new entry reaches a multiple of 5, update the profile
    profile_mgr = context.bot_data["profile"]
    if profile_mgr.profile["total_answers"] % 5 == 0:
        await profile_mgr.analyze_profile(context.bot_data["gemini"])

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    if not text.strip():
        return
    profile_mgr = context.bot_data["profile"]

    # Is it an answer to a personality question?
    pending = context.bot_data.get("pending_personality_q")
    if pending:
        profile_mgr.record_answer(pending, text)
        context.bot_data["pending_personality_q"] = None

        # Update profile every 5 answers
        if profile_mgr.profile["total_answers"] % 5 == 0:
            await profile_mgr.analyze_profile(context.bot_data["gemini"])

        await update.message.reply_text("Thank you, I saved your answer! 📝")
        return

    # Normal chat
    await update.message.reply_chat_action("typing")
    response = ChatAgent.handle(text, context.bot_data["gemini"],
                                    context.bot_data["memory"],
                                    context.bot_data["profile"])
    await update.message.reply_text(response)

# ============================================================
# SCHEDULED TASKS
# ============================================================
async def morning_briefing(app):
    sheets = app.bot_data["sheets"]
    gemini = app.bot_data["gemini"]
    profile_mgr = app.bot_data["profile"]

    tasks = sheets.get_all_rows(config.SHEET_TODO)
    pending = [g for g in tasks if g.get("Status", "").lower() != "tamamlandi" and g.get("Status", "").lower() != "completed"]
    profile_ctx = profile_mgr.get_profile_for_prompt()

    prompt = f"""You are the User's personal assistant. Prepare a short morning briefing.

{profile_ctx}

Date: {now_local().strftime('%Y-%m-%d %A')}
Pending tasks: {json.dumps(pending, ensure_ascii=False)}

Rules: Say good morning, list the tasks, keep it a simple 4-5 line message."""

    response = gemini.chat(prompt, "Prepare my morning briefing")
    await app.bot.send_message(chat_id=config.CHAT_ID, text=response)
    logger.info("Morning briefing sent.")


async def coach_message(app):
    sheets = app.bot_data["sheets"]
    gemini = app.bot_data["gemini"]
    profile_mgr = app.bot_data["profile"]

    daily_data = sheets.get_recent_rows(config.SHEET_GUN_VERI, 10)
    current_time = now_local().strftime("%H:%M")
    current_date = now_local().strftime("%Y-%m-%d")
    profile_ctx = profile_mgr.get_profile_for_prompt()

    prompt = f"""You are the User's performance coach.

{profile_ctx}

DAILY DATA: {json.dumps(daily_data, ensure_ascii=False)}

TASK: Ask how their day went today ({current_date}), what they accomplished today, and what they plan to do tomorrow.
Remind them to answer using /r. Keep it short (3-4 sentences), friendly, and motivating."""

    response = gemini.chat(prompt, f"Time is {current_time}, coach message")
    await app.bot.send_message(chat_id=config.CHAT_ID, text=response)
    logger.info("Coach message sent.")


async def weekly_review(app):
    """Deep weekly analysis using Gemini PRO"""
    sheets = app.bot_data["sheets"]
    gemini = app.bot_data["gemini"]
    profile_mgr = app.bot_data["profile"]

    daily_data = sheets.get_all_rows(config.SHEET_GUN_VERI)
    tasks = sheets.get_all_rows(config.SHEET_TODO)
    projects = sheets.get_all_rows(config.SHEET_PROJELER)
    diary = sheets.get_all_rows(config.SHEET_GUNLUK)
    profile_ctx = profile_mgr.get_profile_for_prompt()

    prompt = f"""You are the User's weekly performance analyst. Perform a DEEP and COMPREHENSIVE analysis.

{profile_ctx}

DATA:
- Daily Data: {json.dumps(daily_data[-20:], ensure_ascii=False)}
- Tasks: {json.dumps(tasks, ensure_ascii=False)}
- Projects: {json.dumps(projects, ensure_ascii=False)}
- Diary: {json.dumps(diary[-10:], ensure_ascii=False)}

REPORT HEADINGS:
1. PERFORMANCE SUMMARY - Planned vs actual, success percentage
2. TASK STATUS - Completed/pending
3. PROJECT PROGRESS - Detailed for each project
4. PERSONALITY-BASED ANALYSIS - Strengths/weaknesses according to the profile
5. DEVELOPMENT SUGGESTIONS - 3 concrete suggestions suited to the personality
6. MOTIVATION - A closing tailored to the personality style"""

    # Use PRO model!
    response = gemini.chat_pro(prompt, "Perform weekly review")

    sheets.append_row(config.SHEET_HAFTALIK, {
        "Date": now_local().strftime("%Y-%m-%d"),
        "WeekNo": str(now_local().isocalendar()[1]),
        "Report": response[:500],
        "SuccessPercentage": ""
    })

    await app.bot.send_message(chat_id=config.CHAT_ID, text=response)
    logger.info("Weekly review sent (Gemini Pro).")


async def personality_question(app):
    """Generate and send dynamic personality question using Gemini"""
    profile_mgr = app.bot_data["profile"]
    gemini = app.bot_data["gemini"]
    
    past_questions = [item['q'] for item in profile_mgr.qa_history.get("questions", [])]
    past_text = json.dumps(past_questions[-20:], ensure_ascii=False)
    
    prompt = f"""You are a psychologist. Ask a single thought-provoking question to get to know the user deeper and analyze their Big Five personality traits (Openness, Conscientiousness, Extraversion, Agreeableness, Neuroticism) and values.
    
You have previously asked these questions (DO NOT REPEAT THEM):
{past_text}

Just write the question. It should be short, clear, and thought-provoking. (Example: "What is the one thing you absolutely cannot tolerate in life, and what does that say about you?")"""

    question = gemini.chat(prompt, "Generate a new personality question.")
    app.bot_data["pending_personality_q"] = question

    await app.bot.send_message(
        chat_id=config.CHAT_ID,
        text=f"🧠 **I want to get to know you:**\n\n_{question}_\n\n_(Just type your answer, I will save it)_",
        parse_mode="Markdown"
    )
    logger.info("Dynamic personality question sent.")


def schedule_personality_questions(scheduler, app):
    """Schedule personality questions at random times during the day"""
    now = now_local()
    
    # After 20 questions are answered, only ask 1 question per day
    profile_mgr = app.bot_data["profile"]
    total_answers = profile_mgr.profile.get("total_answers", 0)
    
    num_questions = 1 if total_answers >= 20 else config.PERSONALITY_QUESTIONS_PER_DAY

    for i in range(num_questions):
        random_hour = random.randint(9, 21)
        random_minute = random.randint(0, 59)
        run_time = now.replace(hour=random_hour, minute=random_minute, second=0, microsecond=0)

        if run_time > now:
            scheduler.add_job(
                personality_question,
                DateTrigger(run_date=run_time),
                args=[app],
                id=f"personality_{i}_{now.strftime('%Y%m%d')}"
            )
            logger.info(f"Personality question scheduled for: {run_time.strftime('%H:%M')}")

# ============================================================
# MAIN PROGRAM
# ============================================================
def main():
    print("=" * 50)
    print("  AI PERSONAL ASSISTANT v2.0")
    print("  Personality Profile + Gemini Pro + Sage Mode")
    print("=" * 50)

    sheets = SheetsManager()
    gemini = GeminiManager()
    memory = MemoryManager()
    profile_mgr = ProfileManager()

    app = Application.builder().token(config.TELEGRAM_TOKEN).build()
    app.bot_data["sheets"] = sheets
    app.bot_data["gemini"] = gemini
    app.bot_data["memory"] = memory
    app.bot_data["profile"] = profile_mgr
    app.bot_data["pending_personality_q"] = None

    # Command handlers
    app.add_handler(CommandHandler("h", cmd_help))
    app.add_handler(CommandHandler("r", cmd_report))
    app.add_handler(CommandHandler("t", cmd_todo))
    app.add_handler(CommandHandler("g", cmd_diary))
    app.add_handler(CommandHandler("p", cmd_project))
    app.add_handler(CommandHandler("bilge", cmd_sage))
    app.add_handler(CommandHandler("profil", cmd_profile))
    app.add_handler(CommandHandler("start", cmd_help))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    # Scheduler
    scheduler = AsyncIOScheduler(timezone=config.TIMEZONE)

    scheduler.add_job(morning_briefing, CronTrigger(hour=config.BRIFING_HOUR, minute=config.BRIFING_MINUTE),
                      args=[app], id="morning_briefing")

    # Send coach message at exactly 23:59 (midnight)
    scheduler.add_job(coach_message, CronTrigger(hour=23, minute=59),
                      args=[app], id="coach_24")

    scheduler.add_job(weekly_review,
                      CronTrigger(day_of_week=config.HAFTALIK_DAY,
                                  hour=config.HAFTALIK_HOUR, minute=config.HAFTALIK_MINUTE),
                      args=[app], id="weekly_review")

    # Schedule new personality questions every day at 03:00
    scheduler.add_job(
        lambda: schedule_personality_questions(scheduler, app),
        CronTrigger(hour=3, minute=0),
        id="plan_personality_questions"
    )

    # Schedule immediately for today
    schedule_personality_questions(scheduler, app)

    scheduler.start()
    logger.info("Scheduler started.")

    print(f"\nPersonality profile: {profile_mgr.profile['total_answers']} questions answered")
    print(f"Scheduled tasks active. Bot is running...\n")

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
