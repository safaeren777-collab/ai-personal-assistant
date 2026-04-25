"""
AI Personal Assistant — Standalone Telegram Bot v2.0

A self-hosted, AI-powered personal assistant that runs as a Telegram bot.
Features include task management, performance tracking, project management,
diary keeping, personality profiling (Big Five model), and scheduled
coaching/review messages.

Tech stack:
    - Google Gemini (Flash + Pro) for AI
    - Google Sheets for persistent data storage
    - APScheduler for scheduled tasks
    - python-telegram-bot for Telegram integration

Author: Safa Eren (github.com/safaeren777-collab)
License: MIT
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
        logger.info("Google Sheets baglantisi kuruldu.")

    def get_sheet(self, name):
        return self.spreadsheet.worksheet(name)

    def get_all_rows(self, sheet_name):
        try:
            sheet = self.get_sheet(sheet_name)
            return sheet.get_all_records()
        except Exception as e:
            logger.error(f"Sheets okuma hatasi ({sheet_name}): {e}")
            return []

    def append_row(self, sheet_name, row_dict):
        try:
            sheet = self.get_sheet(sheet_name)
            headers = sheet.row_values(1)
            row = [row_dict.get(h, "") for h in headers]
            sheet.append_row(row, value_input_option="USER_ENTERED")
            return True
        except Exception as e:
            logger.error(f"Sheets yazma hatasi ({sheet_name}): {e}")
            return False

    def get_recent_rows(self, sheet_name, n=10):
        rows = self.get_all_rows(sheet_name)
        return rows[-n:] if len(rows) > n else rows

# ============================================================
# HAFIZA YONETICISI
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
# KISILIK PROFILI YONETICISI
# ============================================================
class ProfileManager:
    """Big Five + degerler + iletisim tarzi profili"""

    QUESTION_BANK = [
        # Aciklik (Openness)
        "Yeni bir sey denemekten hoslanir misin yoksa bildiklerine mi sadik kalirsin?",
        "Sanat, muzik veya edebiyat seni nasil etkiler?",
        "Hayal kurmaktan hoslanir misin? En son ne hayal ettin?",
        "Farkli kulturleri tanimak seni heyecanlandirir mi?",
        # Sorumluluk (Conscientiousness)
        "Islerini genellikle planlayarak mi yoksa anlık kararlarla mi yaparsin?",
        "Bir projeye basladiginda bitirene kadar odaklanabilir misin?",
        "Detaylara dikkat edersin mi yoksa buyuk resmi mi gorursun?",
        "Daginik mi yoksa duzenli bir calisma ortamin mi var?",
        # Disadonukluk (Extraversion)
        "Kalabalik ortamlarda enerjin artar mi yoksa azalir mi?",
        "Yalniz vakit gecirmeyi mi yoksa insanlarla olmayi mi tercih edersin?",
        "Yeni insanlarla tanismak seni heyecanlandirir mi?",
        "Sessiz bir aksam mi yoksa canli bir bulusma mi tercih edersin?",
        # Uyumluluk (Agreeableness)
        "Birisiyle fikir ayriligi yasadiginda ne yaparsin?",
        "Baskalarinin duygulari seni ne kadar etkiler?",
        "Yardim etmek icin kendi planlarindan vazgecer misin?",
        "Takimda calismayi mi yoksa tek basina mi olmayi tercih edersin?",
        # Duygusal Denge (Neuroticism)
        "Stresli durumlarda nasil tepki verirsin?",
        "Kucuk aksilikler gununu mahveder mi?",
        "Gelecekle ilgili endiselenme egilimin var mi?",
        "Duygularini kontrol edebildigini dusunuyor musun?",
        # Degerler ve Motivasyon
        "Hayatta en cok neye deger veriyorsun?",
        "Basari senin icin ne anlama geliyor?",
        "10 yil sonra kendini nerede goruyorsun?",
        "Hangi konularda uzlasmaz bir tutumun var?",
        # Iletisim Tarzi
        "Sana nasil hitap edilmesinden hoslanirsin - resmi mi samimi mi?",
        "Uzun aciklamalar mi yoksa kisa oz bilgiler mi tercih edersin?",
        "Motivasyon icin sert gercekler mi yoksa pozitif tesvik mi istersin?",
        "Espri tarzin nasil - kuru mu, ince mi, absurt mu?",
        # Yasam Tarzi
        "Sabahci misin gece kusu mu?",
        "Rutin mu sever yoksa spontan mi yasarsin?",
        "En verimli oldugum saat dilimi hangisi dersin?",
        "Sikildikinda ne yaparsin?",
    ]

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
            "communication_style": "samimi ve kisa",
            "motivation_style": "dengeli - bazen sert bazen destekleyici",
            "humor_style": "bilinmiyor",
            "values": [],
            "personality_summary": "Henuz yeterli veri toplanmadi.",
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

    def get_random_question(self):
        asked = set(self.qa_history.get("asked_indices", []))
        available = [i for i in range(len(self.QUESTION_BANK)) if i not in asked]
        if not available:
            self.qa_history["asked_indices"] = []
            available = list(range(len(self.QUESTION_BANK)))
        idx = random.choice(available)
        self.qa_history["asked_indices"].append(idx)
        self._save()
        return self.QUESTION_BANK[idx]

    def record_answer(self, question, answer):
        self.qa_history["questions"].append({
            "q": question,
            "a": answer,
            "date": datetime.now(ZoneInfo(config.TIMEZONE)).strftime("%Y-%m-%d %H:%M")
        })
        self.profile["total_answers"] = len(self.qa_history["questions"])
        self._save()

    def get_profile_summary(self):
        return self.profile.get("personality_summary", "Henuz analiz yapilmadi.")

    def get_profile_for_prompt(self):
        if self.profile["total_answers"] < 3:
            return "Kullanicinin kisilik profili henuz olusturulmadi."
        p = self.profile
        bf = p["big_five"]
        return f"""KULLANICI KISILIK PROFILI:
- Aciklik: {bf['openness']:.1f}/1.0
- Sorumluluk: {bf['conscientiousness']:.1f}/1.0
- Disadonukluk: {bf['extraversion']:.1f}/1.0
- Uyumluluk: {bf['agreeableness']:.1f}/1.0
- Duygusal Hassasiyet: {bf['neuroticism']:.1f}/1.0
- Iletisim Tercihi: {p['communication_style']}
- Motivasyon Tarzi: {p['motivation_style']}
- Espri Tarzi: {p['humor_style']}
- Degerler: {', '.join(p['values']) if p['values'] else 'Belirlenmedi'}
- Ozet: {p['personality_summary']}

BU PROFILE GORE KONUSMA TARZINI AYARLA. Kullanicinin sevdigi tarzi kullan."""

    async def analyze_profile(self, gemini_pro):
        if len(self.qa_history["questions"]) < 5:
            return
        qa_text = json.dumps(self.qa_history["questions"][-30:], ensure_ascii=False)
        prompt = f"""Sen bir kisilik psikoloji uzmanisin. Asagidaki soru-cevaplari analiz ederek Big Five kisilik modeline gore bir profil cikar.

SORU-CEVAPLAR:
{qa_text}

SU FORMATTA JSON DONDUR (baska hicbir sey yazma):
{{
  "big_five": {{
    "openness": 0.0-1.0 arasi,
    "conscientiousness": 0.0-1.0 arasi,
    "extraversion": 0.0-1.0 arasi,
    "agreeableness": 0.0-1.0 arasi,
    "neuroticism": 0.0-1.0 arasi
  }},
  "communication_style": "kisinin tercih ettigi iletisim tarzi",
  "motivation_style": "kisiye en uygun motivasyon yontemi",
  "humor_style": "kisinin espri anlayisi",
  "values": ["deger1", "deger2", "deger3"],
  "personality_summary": "2-3 cumlelik kisilik ozeti"
}}"""
        try:
            response = gemini_pro.chat_pro(prompt, "Kisilik analizi yap")
            text = response.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]
            result = json.loads(text)
            self.profile.update(result)
            self.profile["last_updated"] = datetime.now(ZoneInfo(config.TIMEZONE)).strftime("%Y-%m-%d %H:%M")
            self._save()
            logger.info("Kisilik profili guncellendi!")
        except Exception as e:
            logger.error(f"Profil analiz hatasi: {e}")

# ============================================================
# GEMINI AI MANAGER
# ============================================================
class GeminiManager:
    def __init__(self):
        genai.configure(api_key=config.GEMINI_API_KEY)
        self.model = genai.GenerativeModel(config.GEMINI_MODEL)
        self.model_pro = genai.GenerativeModel(config.GEMINI_MODEL_PRO)
        logger.info("Gemini API baglantisi kuruldu (Flash + Pro).")

    def chat(self, system_prompt, user_message, history=None):
        try:
            messages = []
            if history:
                for msg in history[-config.MEMORY_WINDOW:]:
                    messages.append({"role": msg["role"], "parts": [msg["content"]]})
            chat = self.model.start_chat(history=messages)
            full_prompt = f"[SISTEM TALIMATI]\n{system_prompt}\n\n[KULLANICI MESAJI]\n{user_message}"
            response = chat.send_message(full_prompt)
            return response.text
        except Exception as e:
            logger.error(f"Gemini Flash hatasi: {e}")
            return f"Bir hata olustu: {str(e)}"

    def chat_pro(self, system_prompt, user_message):
        try:
            chat = self.model_pro.start_chat()
            full_prompt = f"[SISTEM TALIMATI]\n{system_prompt}\n\n[KULLANICI MESAJI]\n{user_message}"
            response = chat.send_message(full_prompt)
            return response.text
        except Exception as e:
            logger.error(f"Gemini Pro hatasi: {e}")
            return f"Bir hata olustu: {str(e)}"

# ============================================================
# YARDIMCI
# ============================================================
def now_istanbul():
    return datetime.now(ZoneInfo(config.TIMEZONE))

# ============================================================
# AJANLAR
# ============================================================
class RaporAgent:
    @staticmethod
    def handle(payload, sheets, gemini, memory, profile_mgr):
        data = sheets.get_recent_rows(config.SHEET_GUN_VERI, 15)
        now = now_istanbul().strftime("%Y-%m-%d %H:%M")
        profile_ctx = profile_mgr.get_profile_for_prompt()
        prompt = f"""Sen bir Performans Rapor Ajanisin.

{profile_ctx}

GOREV:
1. Gelecek ifadeler (yapacagim, planliyorum) -> PLAN olarak kaydet.
2. Gecmis ifadeler (yaptim, tamamladim) -> GERCEKLESEN olarak kaydet.
3. Mevcut verileri inceleyerek baglamli cevap ver.

MEVCUT GUN-VERI:
{json.dumps(data, ensure_ascii=False)}

Tarih/saat: {now}"""

        history = memory.get_history("rapor")
        response = gemini.chat(prompt, payload, history)
        memory.add_message("rapor", "user", payload)
        memory.add_message("rapor", "model", response)

        # Her zaman kaydet - /r ile gelen her sey kaydedilmeli
        if any(k in payload.lower() for k in ["goster", "listele", "oku", "ne yapmis", "rapor"]):
            pass  # Sadece okuma istegi, kaydetme
        else:
            rapor_tipi = "PLAN" if any(k in payload.lower() for k in ["yapac", "planl", "hedef", "calis", "calisa"]) else "GERCEKLESEN"
            saved = sheets.append_row(config.SHEET_GUN_VERI, {
                "Tarih": now_istanbul().strftime("%Y-%m-%d"),
                "Saat": now_istanbul().strftime("%H:%M"),
                "Rapor": f"{rapor_tipi}: {payload}"
            })
            if saved and response:
                response += "\n\n\u2705 Kaydedildi!"
        return response


class TodoAgent:
    @staticmethod
    def handle(payload, sheets, gemini, memory, profile_mgr):
        data = sheets.get_all_rows(config.SHEET_TODO)
        now = now_istanbul().strftime("%Y-%m-%d %H:%M")
        profile_ctx = profile_mgr.get_profile_for_prompt()
        prompt = f"""Sen bir To-Do Listesi Yonetim Ajanisin.

{profile_ctx}

GOREV:
1. Yeni gorev -> kaydet. 2. Bitirdim -> Durum guncelle. 3. Goster -> listele.
Kategori varsa kullan (Spor, Ders, Proje vb.)

MEVCUT GOREVLER:
{json.dumps(data, ensure_ascii=False)}

Tarih/saat: {now}"""

        history = memory.get_history("todo")
        response = gemini.chat(prompt, payload, history)
        memory.add_message("todo", "user", payload)
        memory.add_message("todo", "model", response)

        if not any(k in payload.lower() for k in ["listele", "goster", "neler var", "gorevlerim"]):
            kategori, aktivite = "", payload
            if ":" in payload:
                parts = payload.split(":", 1)
                kategori, aktivite = parts[0].strip(), parts[1].strip()
            saved = sheets.append_row(config.SHEET_TODO, {
                "Tarih": now_istanbul().strftime("%Y-%m-%d"),
                "Kategori": kategori, "Aktivite": aktivite, "Durum": "Bekliyor"
            })
            if saved and response:
                response += "\n\n\u2705 Gorev eklendi!"
            elif saved:
                response = "\u2705 Gorev eklendi!"
        return response


class GunlukAgent:
    @staticmethod
    def handle(payload, sheets, gemini, memory, profile_mgr):
        data = sheets.get_recent_rows(config.SHEET_GUNLUK, 15)
        now = now_istanbul().strftime("%Y-%m-%d %H:%M")
        profile_ctx = profile_mgr.get_profile_for_prompt()
        prompt = f"""Sen bir Gunluk Ajanisin.

{profile_ctx}

GOREV: Olay anlatilirsa kaydet. Gecmis sorulursa oku ve yanitla.

MEVCUT GUNLUK:
{json.dumps(data, ensure_ascii=False)}

Tarih/saat: {now}"""

        history = memory.get_history("gunluk")
        response = gemini.chat(prompt, payload, history)
        memory.add_message("gunluk", "user", payload)
        memory.add_message("gunluk", "model", response)

        if not any(k in payload.lower() for k in ["goster", "oku", "ne yapmistim", "gecen"]):
            saved = sheets.append_row(config.SHEET_GUNLUK, {
                "Tarih": now_istanbul().strftime("%Y-%m-%d"), "Gunluk": payload
            })
            if saved and response:
                response += "\n\n\u2705 Gunluge kaydedildi!"
            elif saved:
                response = "\u2705 Gunluge kaydedildi!"
        return response


class ProjeAgent:
    @staticmethod
    def handle(payload, sheets, gemini, memory, profile_mgr):
        data = sheets.get_all_rows(config.SHEET_PROJELER)
        now = now_istanbul().strftime("%Y-%m-%d %H:%M")
        profile_ctx = profile_mgr.get_profile_for_prompt()
        prompt = f"""Sen bir Proje Yonetim Ajanisin.

{profile_ctx}

GOREV: Yeni proje/gorev ekle, durum sor, ilerleme guncelle.
Sutunlar: Proje, AltGorev, Durum, Yuzde, Deadline, Notlar

MEVCUT PROJELER:
{json.dumps(data, ensure_ascii=False)}

Tarih/saat: {now}"""

        history = memory.get_history("proje")
        response = gemini.chat(prompt, payload, history)
        memory.add_message("proje", "user", payload)
        memory.add_message("proje", "model", response)
        return response


class SohbetAgent:
    @staticmethod
    def handle(payload, gemini, memory, profile_mgr):
        now = now_istanbul().strftime("%Y-%m-%d %H:%M")
        profile_ctx = profile_mgr.get_profile_for_prompt()
        prompt = f"""Sen samimi bir sohbet asistanisin.

{profile_ctx}

Tarih/saat: {now}"""

        history = memory.get_history("sohbet")
        response = gemini.chat(prompt, payload, history)
        memory.add_message("sohbet", "user", payload)
        memory.add_message("sohbet", "model", response)
        return response

# ============================================================
# HELP MENUSU
# ============================================================
HELP_TEXT = """🤖 **Kisisel Asistan v2.0**

/r [cevap] - Rapor tablosunu okuyup yazar
/t [gorev] - To-Do listesini yonetir
/g [ani] - Gunlugu okuyup yazar
/p [proje] - Proje takibi yapar
/profil - Kisilik profilini goster
/h - Bu menuyu gosterir

_(Komutsuz yazilar standart sohbete gider)_
_(Gun icinde rastgele kisilik sorulari gelecek)_"""

# ============================================================
# TELEGRAM HANDLERS
# ============================================================
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")

async def cmd_rapor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payload = " ".join(context.args) if context.args else "Son raporlarimi goster"
    await update.message.reply_chat_action("typing")
    response = RaporAgent.handle(payload, context.bot_data["sheets"],
                                  context.bot_data["gemini"], context.bot_data["memory"],
                                  context.bot_data["profile"])
    await update.message.reply_text(response)

async def cmd_todo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payload = " ".join(context.args) if context.args else "Gorevlerimi listele"
    await update.message.reply_chat_action("typing")
    response = TodoAgent.handle(payload, context.bot_data["sheets"],
                                 context.bot_data["gemini"], context.bot_data["memory"],
                                 context.bot_data["profile"])
    await update.message.reply_text(response)

async def cmd_gunluk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payload = " ".join(context.args) if context.args else "Son gunluk kayitlarimi goster"
    await update.message.reply_chat_action("typing")
    response = GunlukAgent.handle(payload, context.bot_data["sheets"],
                                    context.bot_data["gemini"], context.bot_data["memory"],
                                    context.bot_data["profile"])
    await update.message.reply_text(response)

async def cmd_proje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payload = " ".join(context.args) if context.args else "Proje durumlarini goster"
    await update.message.reply_chat_action("typing")
    response = ProjeAgent.handle(payload, context.bot_data["sheets"],
                                   context.bot_data["gemini"], context.bot_data["memory"],
                                   context.bot_data["profile"])
    await update.message.reply_text(response)

async def cmd_profil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kisilik profilini goster"""
    profile_mgr = context.bot_data["profile"]
    p = profile_mgr.profile
    bf = p["big_five"]

    text = f"""🧠 **Kisilik Profilin**

📊 **Big Five Skorlari:**
• Aciklik: {'█' * int(bf['openness']*10)}{'░' * (10-int(bf['openness']*10))} {bf['openness']:.1f}
• Sorumluluk: {'█' * int(bf['conscientiousness']*10)}{'░' * (10-int(bf['conscientiousness']*10))} {bf['conscientiousness']:.1f}
• Disadonukluk: {'█' * int(bf['extraversion']*10)}{'░' * (10-int(bf['extraversion']*10))} {bf['extraversion']:.1f}
• Uyumluluk: {'█' * int(bf['agreeableness']*10)}{'░' * (10-int(bf['agreeableness']*10))} {bf['agreeableness']:.1f}
• Hassasiyet: {'█' * int(bf['neuroticism']*10)}{'░' * (10-int(bf['neuroticism']*10))} {bf['neuroticism']:.1f}

💬 Iletisim: {p['communication_style']}
🎯 Motivasyon: {p['motivation_style']}
😄 Espri: {p['humor_style']}
💎 Degerler: {', '.join(p['values']) if p['values'] else 'Henuz belirlenmedi'}

📝 {p['personality_summary']}

_Toplam {p['total_answers']} soru cevaplanmis. Son guncelleme: {p.get('last_updated', 'Henuz yapilmadi')}_"""

    await update.message.reply_text(text)

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    if not text.strip():
        return
    profile_mgr = context.bot_data["profile"]

    # Kisilik sorusuna cevap mi?
    pending = context.bot_data.get("pending_personality_q")
    if pending:
        profile_mgr.record_answer(pending, text)
        context.bot_data["pending_personality_q"] = None

        # Her 5 cevapta bir profil guncelle
        if profile_mgr.profile["total_answers"] % 5 == 0:
            await profile_mgr.analyze_profile(context.bot_data["gemini"])

        await update.message.reply_text("Tesekkurler, cevabini kaydettim! 📝")
        return

    # Normal sohbet
    await update.message.reply_chat_action("typing")
    response = SohbetAgent.handle(text, context.bot_data["gemini"],
                                    context.bot_data["memory"],
                                    context.bot_data["profile"])
    await update.message.reply_text(response)

# ============================================================
# ZAMANLI GOREVLER
# ============================================================
async def sabah_brifing(app):
    sheets = app.bot_data["sheets"]
    gemini = app.bot_data["gemini"]
    profile_mgr = app.bot_data["profile"]

    gorevler = sheets.get_all_rows(config.SHEET_TODO)
    bekleyenler = [g for g in gorevler if g.get("Durum", "").lower() != "tamamlandi"]
    profile_ctx = profile_mgr.get_profile_for_prompt()

    prompt = f"""Sen benim kisisel asistanimsin. Kisa bir sabah brifingi hazirla.

{profile_ctx}

Tarih: {now_istanbul().strftime('%Y-%m-%d %A')}
Bekleyen gorevler: {json.dumps(bekleyenler, ensure_ascii=False)}

Kurallar: Gunaydin de, gorevleri listele, 4-5 satir sade mesaj."""

    response = gemini.chat(prompt, "Sabah brifingimi hazirla")
    await app.bot.send_message(chat_id=config.CHAT_ID, text=response)
    logger.info("Sabah brifingi gonderildi.")


async def koc_mesaj(app):
    sheets = app.bot_data["sheets"]
    gemini = app.bot_data["gemini"]
    profile_mgr = app.bot_data["profile"]

    gun_veri = sheets.get_recent_rows(config.SHEET_GUN_VERI, 10)
    saat = now_istanbul().strftime("%H:%M")
    tarih = now_istanbul().strftime("%Y-%m-%d")
    profile_ctx = profile_mgr.get_profile_for_prompt()

    prompt = f"""Sen Safa'nin performans kocusun.

{profile_ctx}

GUN-VERI: {json.dumps(gun_veri, ensure_ascii=False)}

GOREV: Bugun ({tarih}) PLAN varsa hatırlat. 4 saat ne yaptin, siradaki plan ne sor.
/r ile cevap vermesini hatırlat. Saat {saat}'a gore ton ayarla.
Kisa (3-4 cumle), samimi ama sert."""

    response = gemini.chat(prompt, f"Saat {saat}, koc mesaji")
    await app.bot.send_message(chat_id=config.CHAT_ID, text=response)
    logger.info(f"Koc mesaji gonderildi (saat {saat}).")


async def haftalik_degerlendirme(app):
    """Gemini PRO ile derin haftalik analiz"""
    sheets = app.bot_data["sheets"]
    gemini = app.bot_data["gemini"]
    profile_mgr = app.bot_data["profile"]

    gun_veri = sheets.get_all_rows(config.SHEET_GUN_VERI)
    gorevler = sheets.get_all_rows(config.SHEET_TODO)
    projeler = sheets.get_all_rows(config.SHEET_PROJELER)
    gunluk = sheets.get_all_rows(config.SHEET_GUNLUK)
    profile_ctx = profile_mgr.get_profile_for_prompt()

    prompt = f"""Sen Safa'nin haftalik performans analistisin. DERIN ve KAPSAMLI bir analiz yap.

{profile_ctx}

VERILER:
- Gun-veri: {json.dumps(gun_veri[-20:], ensure_ascii=False)}
- Gorevler: {json.dumps(gorevler, ensure_ascii=False)}
- Projeler: {json.dumps(projeler, ensure_ascii=False)}
- Gunluk: {json.dumps(gunluk[-10:], ensure_ascii=False)}

RAPOR BASLIKLARI:
1. PERFORMANS OZETI - Plan vs gerceklesen, basari yuzdesi
2. GOREV DURUMU - Tamamlanan/bekleyen
3. PROJE ILERLEMESI - Her proje detayli
4. KISILIK BAZLI ANALIZ - Profiline gore guclu/zayif yanlari
5. GELISIM ONERILERI - 3 somut, kisilige uygun oneri
6. MOTIVASYON - Kisilik tarzina uygun kapatis"""

    # PRO model kullan!
    response = gemini.chat_pro(prompt, "Haftalik degerlendirme yap")

    sheets.append_row(config.SHEET_HAFTALIK, {
        "Tarih": now_istanbul().strftime("%Y-%m-%d"),
        "HaftaNo": str(now_istanbul().isocalendar()[1]),
        "Rapor": response[:500],
        "BasariYuzdesi": ""
    })

    await app.bot.send_message(chat_id=config.CHAT_ID, text=response)
    logger.info("Haftalik degerlendirme gonderildi (Gemini Pro).")


async def kisilik_sorusu(app):
    """Rastgele zamanlarda kisilik sorusu gonder"""
    profile_mgr = app.bot_data["profile"]
    question = profile_mgr.get_random_question()
    app.bot_data["pending_personality_q"] = question

    await app.bot.send_message(
        chat_id=config.CHAT_ID,
        text=f"🧠 **Seni tanimak istiyorum:**\n\n_{question}_\n\n_(Cevabini aynen yaz, ben kaydedecegim)_",
        parse_mode="Markdown"
    )
    logger.info("Kisilik sorusu gonderildi.")


def schedule_personality_questions(scheduler, app):
    """Gun icinde rastgele saatlerde kisilik sorulari planla"""
    now = now_istanbul()
    today_start = now.replace(hour=9, minute=0, second=0, microsecond=0)
    today_end = now.replace(hour=22, minute=0, second=0, microsecond=0)

    for i in range(config.PERSONALITY_QUESTIONS_PER_DAY):
        random_hour = random.randint(9, 21)
        random_minute = random.randint(0, 59)
        run_time = now.replace(hour=random_hour, minute=random_minute, second=0, microsecond=0)

        if run_time > now:
            scheduler.add_job(
                kisilik_sorusu,
                DateTrigger(run_date=run_time),
                args=[app],
                id=f"personality_{i}_{now.strftime('%Y%m%d')}"
            )
            logger.info(f"Kisilik sorusu planlanandi: {run_time.strftime('%H:%M')}")

# ============================================================
# ANA PROGRAM
# ============================================================
def main():
    print("=" * 50)
    print("  AKILLI KISISEL ASISTAN v2.0")
    print("  Kisilik Profili + Gemini Pro")
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

    # Komut handler'lari
    app.add_handler(CommandHandler("h", cmd_help))
    app.add_handler(CommandHandler("r", cmd_rapor))
    app.add_handler(CommandHandler("t", cmd_todo))
    app.add_handler(CommandHandler("g", cmd_gunluk))
    app.add_handler(CommandHandler("p", cmd_proje))
    app.add_handler(CommandHandler("profil", cmd_profil))
    app.add_handler(CommandHandler("start", cmd_help))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    # Zamanlayici
    scheduler = AsyncIOScheduler(timezone=config.TIMEZONE)

    scheduler.add_job(sabah_brifing, CronTrigger(hour=config.BRIFING_HOUR, minute=config.BRIFING_MINUTE),
                      args=[app], id="sabah_brifing")

    for saat in config.KOC_HOURS:
        scheduler.add_job(koc_mesaj, CronTrigger(hour=saat, minute=0),
                          args=[app], id=f"koc_{saat}")

    scheduler.add_job(haftalik_degerlendirme,
                      CronTrigger(day_of_week=config.HAFTALIK_DAY,
                                  hour=config.HAFTALIK_HOUR, minute=config.HAFTALIK_MINUTE),
                      args=[app], id="haftalik")

    # Her gun 03:00'da yeni kisilik sorulari planla
    scheduler.add_job(
        lambda: schedule_personality_questions(scheduler, app),
        CronTrigger(hour=3, minute=0),
        id="plan_personality_questions"
    )

    # Bugun icin de hemen planla
    schedule_personality_questions(scheduler, app)

    scheduler.start()
    logger.info("Zamanlayici baslatildi.")

    print(f"\nKisilik profili: {profile_mgr.profile['total_answers']} soru cevaplanmis")
    print(f"Zamanli gorevler aktif. Bot calisiyor...\n")

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
