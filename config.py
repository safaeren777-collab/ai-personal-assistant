# -*- coding: utf-8 -*-
"""
Configuration module for the AI Personal Assistant.
Loads sensitive values from environment variables (.env file).
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

def _require(key: str) -> str:
    """Get required environment variable or exit with helpful error."""
    value = os.getenv(key)
    if not value:
        print(f"\n[ERROR] Missing required environment variable: {key}")
        print(f"  -> Copy .env.example to .env and fill in your values.")
        print(f"  -> See README.md for setup instructions.\n")
        sys.exit(1)
    return value

# ============================================================
# Telegram Bot
# ============================================================
TELEGRAM_TOKEN = _require("TELEGRAM_TOKEN")
CHAT_ID = int(_require("CHAT_ID"))

# ============================================================
# Google Gemini AI
# ============================================================
GEMINI_API_KEY = _require("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_MODEL_PRO = os.getenv("GEMINI_MODEL_PRO", "gemini-2.5-pro")

# ============================================================
# Google Sheets
# ============================================================
SHEETS_CREDENTIALS_FILE = os.getenv("SHEETS_CREDENTIALS_FILE", "credentials.json")
SPREADSHEET_ID = _require("SPREADSHEET_ID")

# Sheet names (customize if your sheets have different names)
SHEET_GUN_VERI = os.getenv("SHEET_GUN_VERI", "g\u00fcn-veri")
SHEET_TODO = os.getenv("SHEET_TODO", "to-do list")
SHEET_GUNLUK = os.getenv("SHEET_GUNLUK", "gunluk")
SHEET_PROJELER = os.getenv("SHEET_PROJELER", "projeler")
SHEET_HAFTALIK = os.getenv("SHEET_HAFTALIK", "haftalik-degerlendirme")

# ============================================================
# Scheduling (Istanbul timezone by default)
# ============================================================
TIMEZONE = os.getenv("TIMEZONE", "Europe/Istanbul")
BRIFING_HOUR = int(os.getenv("BRIFING_HOUR", "8"))
BRIFING_MINUTE = int(os.getenv("BRIFING_MINUTE", "0"))
KOC_HOURS = [int(h) for h in os.getenv("KOC_HOURS", "12,16,20,0").split(",")]
HAFTALIK_DAY = os.getenv("HAFTALIK_DAY", "mon")
HAFTALIK_HOUR = int(os.getenv("HAFTALIK_HOUR", "0"))
HAFTALIK_MINUTE = int(os.getenv("HAFTALIK_MINUTE", "30"))

# ============================================================
# Memory & Personality
# ============================================================
MEMORY_FILE = os.getenv("MEMORY_FILE", "memory.json")
MEMORY_WINDOW = int(os.getenv("MEMORY_WINDOW", "10"))
PROFILE_FILE = os.getenv("PROFILE_FILE", "profile.json")
PROFILE_QA_FILE = os.getenv("PROFILE_QA_FILE", "profile_qa.json")
PERSONALITY_QUESTIONS_PER_DAY = int(os.getenv("PERSONALITY_QUESTIONS_PER_DAY", "3"))
