# 🚀 24/7 Free Render Deployment Guide for Nym

This guide shows you how to deploy **Project Nym** to [Render](https://render.com) for **100% FREE** with **automatic deployments on `git push`** and **24/7 continuous uptime**.

---

## ⚡ How It Works (100% Free 24/7)

1. **Auto-Deploy on `git push`**: Render links to your GitHub repository. Every time you push code (`git push origin main`), Render rebuilds and redeploys Nym automatically.
2. **Embedded HTTP Health Server**: Nym runs a lightweight HTTP server on `/health` (port 10000).
3. **30-Min Upstash Heartbeat**: Nym automatically pings Upstash Redis every 30 minutes to log system health and keep Redis warmed up.
4. **24/7 Keep-Alive Monitor**: A free external pinger (like [UptimeRobot](https://uptimerobot.com) or [Cron-Job.org](https://cron-job.org)) pings `https://<your-render-app>.onrender.com/health` every 5–10 minutes. This prevents Render from spinning down your bot, keeping it **online forever at $0 cost**.

---

## 🛠️ Step-by-Step Setup

### Step 1: Push Code to GitHub
Ensure your code is pushed to a GitHub repository:
```bash
git add .
git commit -m "Add Render auto-deploy and 24/7 health check setup"
git push origin main
```

---

### Step 2: Create Web Service on Render
1. Go to your [Render Dashboard](https://dashboard.render.com).
2. Click **New +** -> **Web Service**.
3. Connect your GitHub repository.
4. Fill in the following settings:
   - **Name**: `project-nym` (or any name you prefer)
   - **Region**: Choose closest to your users
   - **Branch**: `main` (or `master`)
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python main.py`
   - **Instance Type**: **Free** ($0/month)
5. Scroll down to **Environment Variables** and add:
   - `DISCORD_TOKEN` = `your_discord_token`
   - `OPENROUTER_KEY` = `your_openrouter_key`
   - `UPSTASH_REDIS_REST_URL` = `https://great-camel-72413.upstash.io`
   - `UPSTASH_REDIS_REST_TOKEN` = `your_upstash_token`
   - `PORT` = `10000`
   - `DB_PATH` = `nym.db`
   - `LOG_LEVEL` = `INFO`
6. Click **Create Web Service**. Render will deploy Nym and provide your public URL (e.g. `https://project-nym.onrender.com`).

---

### Step 3: Enable 24/7 Keep-Alive Ping (Free)
To ensure Render never puts your bot to sleep after 15 minutes of inactivity:
1. Create a free account at [UptimeRobot.com](https://uptimerobot.com) or [Cron-Job.org](https://cron-job.org).
2. Click **Add New Monitor**.
3. Settings:
   - **Monitor Type**: HTTP(s)
   - **Friendly Name**: `Nym Bot Health Check`
   - **URL**: `https://<your-render-app-name>.onrender.com/health`
   - **Monitoring Interval**: Every `5 minutes` or `10 minutes`
4. Click **Create Monitor**.

🎉 **That's it!**
Your bot will now:
- Automatically redeploy on every `git push`.
- Stay online **24/7/365** completely free.
- Log Upstash Redis health checks every 30 minutes.
