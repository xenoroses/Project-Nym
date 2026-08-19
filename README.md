---
title: Nym Bot
emoji: 🌙
colorFrom: blue
colorTo: purple
sdk: gradio
app_file: app.py
pinned: false
---

# Nym - Py-Cord Discord Bot

A modern, production-ready Discord bot for **Project Nym**, built with **Python 3.11+**, **Py-Cord**, and an asynchronous modular cogs architecture.

---

## 📁 Project Structure

```text
Project Nym/
├── .venv/              # Python virtual environment
├── src/
│   ├── cogs/           # Command modules (one file per feature/category)
│   │   └── general.py  # Example cog with /ping and /info slash commands
│   ├── config/         # Settings loader and environment variable validator
│   │   └── settings.py
│   ├── database/       # Async SQLite database connection & schema models
│   │   └── db.py
│   ├── events/         # Discord event listeners (on_ready, etc.)
│   │   └── on_ready.py
│   ├── utils/          # Shared helpers (colorlog setup, embeds, etc.)
│   │   ├── logger.py
│   │   └── embeds.py
│   ├── views/          # Discord UI components (Buttons, Selects, Modals)
│   │   └── confirm_view.py
│   └── bot.py          # NymBot class & auto-extension loader
├── logs/               # Application log output directory (nym.log)
├── .env                # Local secrets configuration (Git ignored)
├── .env.example        # Shared environment template
├── .gitignore          # Git ignore rules
├── main.py             # Main entry point
├── requirements.txt    # Frozen dependency manifest
└── README.md           # Documentation
```

---

## 🛠️ Prerequisites

- **Python 3.11** or higher installed.
- A **Discord Application & Bot Token** from the [Discord Developer Portal](https://discord.com/developers/applications).

---

## 🚀 Getting Started

### 1. Clone & Navigate
```bash
git clone <your-repository-url>
cd "Project Nym"
```

### 2. Create & Activate Virtual Environment

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Linux / macOS:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Secrets
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Open `.env` and fill in your Discord Bot credentials:
```env
DISCORD_TOKEN=your_actual_discord_bot_token_here
OWNER_ID=123456789012345678
GUILD_ID=123456789012345678
DB_PATH=nym.db
LOG_LEVEL=INFO
```

---

## ▶️ Running Nym Bot

Execute the main entry point:
```bash
python main.py
```

---

## 🧩 Extending Nym Bot

### Adding a New Cog (Commands)
1. Create a new `.py` file inside `src/cogs/` (e.g. `src/cogs/moderation.py`).
2. Implement your Cog class inheriting from `discord.ext.commands.Cog`:
   ```python
   import discord
   from discord.ext import commands

   class Moderation(commands.Cog):
       def __init__(self, bot: commands.Bot):
           self.bot = bot

       @discord.slash_command(name="kick", description="Kick a member.")
       async def kick(self, ctx: discord.ApplicationContext, member: discord.Member):
           await ctx.respond(f"Kicked {member.mention}!", ephemeral=True)

   def setup(bot: commands.Bot):
       bot.add_cog(Moderation(bot))
   ```
3. Restart the bot. `NymBot` will **automatically discover and load** any python file in `src/cogs/`.

### Adding a New Event Listener
1. Create a new `.py` file inside `src/events/` (e.g. `src/events/on_member_join.py`).
2. Implement your event listener:
   ```python
   import discord
   from discord.ext import commands

   class OnMemberJoin(commands.Cog):
       def __init__(self, bot: commands.Bot):
           self.bot = bot

       @commands.Cog.listener()
       async def on_member_join(self, member: discord.Member):
           print(f"{member.name} joined {member.guild.name}!")

   def setup(bot: commands.Bot):
       bot.add_cog(OnMemberJoin(bot))
   ```

### Working with the Database
Use `self.bot.db` in any cog or event listener:
```python
# Querying records
user = await self.bot.db.fetch_one("SELECT * FROM users WHERE user_id = ?", (ctx.author.id,))

# Executing updates
await self.bot.db.execute("INSERT OR REPLACE INTO users (user_id, username) VALUES (?, ?)", (ctx.author.id, ctx.author.name))
```

---

## 📜 License
This project is open-source and maintained under Project Nym.
