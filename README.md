# 🤖 Video Downloader & Forwarder Telegram Bot

Yeh bot video URLs se MP4 download karta hai aur media group mein channel/group mein forward karta hai.

---

## ⚙️ Setup (Local ya Server pe)

### Step 1 — Bot Token lo
1. Telegram pe [@BotFather](https://t.me/BotFather) pe jaao
2. `/newbot` likho
3. Naam aur username do
4. Token copy karo (looks like: `123456:ABCdef...`)

### Step 2 — Channel/Group ID lo
1. Apne channel/group mein [@userinfobot](https://t.me/userinfobot) add karo
2. Koi bhi message bhejo — ID milega (like `-1001234567890`)
3. **Bot ko channel/group ka Admin banao** (required for sending)

### Step 3 — Install karo
```bash
pip install -r requirements.txt
```

### Step 4 — Run karo
```bash
BOT_TOKEN="your_token_here" FORWARD_CHAT_ID="-1001234567890" python bot.py
```

---

## 🚀 Koyeb pe Free Host karo

1. GitHub pe yeh files upload karo (new repo banao)
2. [koyeb.com](https://koyeb.com) pe free account banao
3. "Create App" → "GitHub" → repo chunno
4. **Environment Variables** mein daalo:
   - `BOT_TOKEN` = aapka bot token
   - `FORWARD_CHAT_ID` = channel/group ID (e.g. `-1001234567890`)
5. Run command: `python bot.py`
6. Deploy! ✅

## 🚀 Railway pe Host karo

1. [railway.app](https://railway.app) pe GitHub se login
2. "New Project" → "Deploy from GitHub repo"
3. Variables mein `BOT_TOKEN` aur `FORWARD_CHAT_ID` daalo
4. Deploy ho jaayega automatically

---

## 📌 Bot Commands

| Command | Kaam |
|---------|------|
| `/start` | Help message |
| `/dl <URL>` | Single video download & forward |
| `/batch` | Batch mode ON karo |
| `/send` | Queue mein saare videos forward karo |
| `/clear` | Queue saaf karo |
| `/status` | Queue check karo |

---

## 📦 Batch Mode (100 Videos)

```
/batch
<URL1>
<URL2>
<URL3>
...
/send
```

---

## 🔗 Supported Sites
YouTube, Instagram, TikTok, Facebook, Twitter/X, Vimeo aur 1000+ sites

---

## ⚠️ Important Notes
- Bot ko channel/group mein **Admin** banana zaroori hai
- Environment variables mein API keys rakho — code mein nahi
- Free hosting mein ek baar mein zyada bade videos slow ho sakte hain
