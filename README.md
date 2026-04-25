<div align="center">

# 🤖 AI Personal Assistant

**A self-hosted, AI-powered personal assistant running on Telegram**

Built with Python • Google Gemini • Google Sheets • APScheduler

[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)](https://python.org)
[![Gemini](https://img.shields.io/badge/Google%20Gemini-AI-orange?logo=google&logoColor=white)](https://ai.google.dev)
[![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4?logo=telegram&logoColor=white)](https://core.telegram.org/bots)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

</div>

---

## ✨ Features

| Command | Feature | Description |
|---------|---------|-------------|
| `/r` | 📊 **Performance Reports** | Track daily plans vs actual achievements |
| `/t` | ✅ **Task Management** | Add, list, and complete tasks with categories |
| `/g` | 📔 **Daily Journal** | Keep a personal diary with AI-powered reflections |
| `/p` | 🗂️ **Project Tracking** | Manage projects with subtasks, deadlines, and progress % |
| `/profil` | 🧠 **Personality Profile** | Big Five personality analysis based on your answers |
| `/h` | ❓ **Help Menu** | Show all available commands |
| _any text_ | 💬 **AI Chat** | General conversation powered by Gemini |

### 🔔 Automated Features (Scheduled)

| Schedule | Feature |
|----------|---------|
| ☀️ **08:00 daily** | Morning briefing with pending tasks |
| 🏋️ **Every 4 hours** | Performance coach — asks what you did and plans next |
| 📈 **Monday 00:30** | Weekly review using Gemini Pro — deep analysis of your entire week |
| 🧠 **Random (3x/day)** | Personality questions to build your psychological profile |

### 🎭 Adaptive Personality System

The bot uses the **Big Five (OCEAN) personality model** to understand you:

- Asks random psychological questions throughout the day
- Analyzes answers using Gemini Pro to build your profile
- **All agents adapt their communication style** to match your personality
- View your profile anytime with `/profil`:

```
🧠 Your Personality Profile

📊 Big Five Scores:
• Openness:          ████████░░ 0.8
• Conscientiousness:  ██████░░░░ 0.6
• Extraversion:       ████░░░░░░ 0.4
• Agreeableness:      ███████░░░ 0.7
• Neuroticism:        ███░░░░░░░ 0.3
```

---

## 🏗️ Architecture

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Telegram    │────▶│  Command Router  │────▶│   AI Agents     │
│  Bot API     │◀────│  /r /t /g /p /h  │◀────│  (Gemini Flash) │
└─────────────┘     └──────────────────┘     └────────┬────────┘
                                                      │
                    ┌──────────────────┐               │
                    │   Scheduler      │               ▼
                    │   (APScheduler)  │        ┌─────────────┐
                    │  • Morning brief │───────▶│ Google      │
                    │  • Coach (4h)    │        │ Sheets API  │
                    │  • Weekly review │        └─────────────┘
                    │  • Personality Q │               │
                    └──────────────────┘               ▼
                                               ┌─────────────┐
                    ┌──────────────────┐        │ Personality │
                    │  Gemini Pro      │◀───────│ Profile     │
                    │  (Weekly + Prof) │        │ (Big Five)  │
                    └──────────────────┘        └─────────────┘
```

---

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- A Telegram Bot Token ([get from @BotFather](https://t.me/BotFather))
- Google Gemini API Key ([get from AI Studio](https://aistudio.google.com/apikey))
- Google Sheets Service Account ([setup guide](https://docs.gspread.org/en/latest/oauth2.html#for-bots-using-service-account))

### 1. Clone the repository

```bash
git clone https://github.com/safaeren777-collab/ai-personal-assistant.git
cd ai-personal-assistant
```

### 2. Install dependencies

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
nano .env  # Fill in your API keys
```

### 4. Set up Google Sheets

Create a Google Spreadsheet with these sheets and headers:

| Sheet Name | Column Headers |
|------------|---------------|
| `gün-veri` | Tarih, Saat, Rapor |
| `to-do list` | Tarih, Kategori, Aktivite, Durum |
| `gunluk` | Tarih, Gunluk |
| `projeler` | Proje, AltGorev, Durum, Yuzde, Deadline, Notlar |
| `haftalik-degerlendirme` | Tarih, HaftaNo, Rapor, BasariYuzdesi |

Share the spreadsheet with your service account email.

### 5. Add credentials

Place your Google Service Account JSON file as `credentials.json` in the project root.

### 6. Run

```bash
python bot.py
```

### 🐧 Deploy as a Service (Linux VPS)

```bash
# Create systemd service
sudo nano /etc/systemd/system/ai-assistant.service
```

```ini
[Unit]
Description=AI Personal Assistant Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/path/to/ai-personal-assistant
ExecStart=/path/to/ai-personal-assistant/venv/bin/python bot.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable ai-assistant
sudo systemctl start ai-assistant
```

---

## 🛠️ Tech Stack

| Technology | Purpose |
|-----------|---------|
| [Python 3.10+](https://python.org) | Core language |
| [Google Gemini](https://ai.google.dev) | AI engine (Flash for daily, Pro for analysis) |
| [python-telegram-bot](https://python-telegram-bot.org) | Telegram Bot API wrapper |
| [gspread](https://docs.gspread.org) | Google Sheets integration |
| [APScheduler](https://apscheduler.readthedocs.io) | Scheduled tasks (cron-based) |
| [python-dotenv](https://pypi.org/project/python-dotenv/) | Environment variable management |

---

## 📁 Project Structure

```
ai-personal-assistant/
├── bot.py              # Main application (768 lines)
├── config.py           # Configuration (reads from .env)
├── requirements.txt    # Python dependencies
├── .env.example        # Environment template
├── .gitignore          # Excluded files
├── LICENSE             # MIT License
└── README.md           # This file
```

**Runtime files (auto-generated, not tracked by git):**
```
├── memory.json         # Conversation history
├── profile.json        # Personality profile data
├── profile_qa.json     # Personality Q&A history
└── credentials.json    # Google service account (secret)
```

---

## 🤝 Contributing

Contributions are welcome! Feel free to:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

<div align="center">

**Built with ❤️ by [Safa Eren](https://github.com/safaeren777-collab)**

</div>
