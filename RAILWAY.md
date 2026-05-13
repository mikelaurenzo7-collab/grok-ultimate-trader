# 🚂 RAILWAY DEPLOYMENT GUIDE

> Deploy the Kalshi Bot in 5 minutes. No servers. No SSH passwords. No headache.

---

## STEP 1: Push Code to GitHub

### Option A: From Your Phone (GitHub App)
1. Download **GitHub** app
2. Create repo `kalshi-bot`
3. Tap **Add files** → Upload all bot files

### Option B: From Terminal (If You Have One)
```bash
git init
git add .
git commit -m "Kalshi bot v1"
git branch -M main
git remote add origin https://github.com/YOURNAME/kalshi-bot.git
git push -u origin main
```

### Option C: ZIP Upload (Easiest!)
1. Go to [github.com](https://github.com) in browser
2. Create repo `kalshi-bot`
3. Click **uploading an existing file**
4. Drag/drop all bot files
5. Commit

---

## STEP 2: Deploy on Railway

1. Go to [railway.app](https://railway.app)
2. Sign up with GitHub (one click!)
3. Click **New Project**
4. Click **Deploy from GitHub repo**
5. Select your `kalshi-bot` repo
6. Railway auto-detects everything and deploys! 🎉

---

## STEP 3: Set Environment Variables

In Railway dashboard:

1. Click your project
2. Click **Variables** tab
3. Add these:

| Variable | Value | Description |
|----------|-------|-------------|
| `SIMULATOR_MODE` | `true` | Start with paper trading |
| `KALSHI_KEY_ID` | *(your key)* | From Kalshi dashboard |
| `KALSHI_SANDBOX` | `true` | Use demo environment |
| `CAPITAL` | `500` | Starting capital |
| `MAX_DAILY_LOSS_PCT` | `0.05` | 5% daily stop-loss |
| `MAX_PER_TRADE_PCT` | `0.02` | 2% max per trade |
| `ACTIVE_STRATEGIES` | `fav_longshot,intra_arb` | Which strategies |

---

## STEP 4: View Logs

In Railway dashboard:
- Click **Deployments**
- Click latest deploy
- See live logs! 📊

---

## 💰 RAILWAY PRICING

| Plan | Cost | Good For |
|------|------|----------|
| **Free** | $0 | Testing, limited hours |
| **Hobby** | ~$5/month | 24/7 bot, persistent |
| **Pro** | $20+/month | Multiple bots, heavy use |

For a $500 trading bot, **Hobby plan ($5/mo)** is perfect.

---

## ⚠️ IMPORTANT NOTES

1. **Ephemeral Storage:** SQLite resets on redeploy. That's fine for testing!
2. **For Live Trading:** Use a persistent volume or external DB (Railway PostgreSQL)
3. **Sleep Mode:** Free tier sleeps after inactivity. Hobby stays awake.

---

## 🎯 QUICK CHECKLIST

- [ ] GitHub repo created
- [ ] All bot files uploaded
- [ ] Railway project created
- [ ] Environment variables set
- [ ] Bot deployed and running
- [ ] Logs show trades!

---

**Ready? Go to [railway.app](https://railway.app) and deploy!** 🚀
