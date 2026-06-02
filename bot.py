import telebot
import requests
import os
import threading
import time
from datetime import datetime
from pymongo import MongoClient
from keep_alive import keep_alive

# ===== CONFIG =====
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8690095871:AAHVf3A932fWfPxga5GMFWEPo2MVT_Pwnvs")
TARGET_GROUP_ID = int(os.environ.get("TARGET_GROUP_ID", "-1003984128597"))
API_URL = "https://vidbunker-backend.dailyweb577.workers.dev/api/download"
MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://Newpaymentsystem:Bt8ORL0eECtlShZE@cluster0.v1ipgab.mongodb.net/?appName=Cluster0")
OWNER_ID = 8558028487

# ===== MongoDB =====
client = MongoClient(MONGO_URI)
db = client["vidbunker_bot"]
downloads_col = db["downloads"]
users_col = db["users"]
groups_col = db["forward_groups"]

bot = telebot.TeleBot(BOT_TOKEN)

# ===== HELPERS =====
def is_owner(message):
    return message.from_user.id == OWNER_ID

def get_forward_groups():
    return [g["chat_id"] for g in groups_col.find({"active": True})]

def save_user(message):
    try:
        users_col.update_one(
            {"user_id": message.from_user.id},
            {"$set": {
                "user_id": message.from_user.id,
                "username": message.from_user.username,
                "name": message.from_user.first_name,
                "last_seen": datetime.now()
            }},
            upsert=True
        )
    except:
        pass

# ===== DOWNLOAD & SEND =====
def process_video(message, link, thumb_bytes=None, index=1, total=1):
    filename = f"vid_{message.message_id}_{index}.mp4"
    thumb_file = f"thumb_{message.message_id}_{index}.jpg"
    prefix = f"╔ [{index}/{total}]\n" if total > 1 else ""

    try:
        status = bot.reply_to(
            message,
            f"{prefix}"
            f"╔════════════════════╗\n"
            f"║   🎬 *VidBunker Bot*   ║\n"
            f"╚════════════════════╝\n\n"
            f"⏳ *Downloading started...*\n"
            f"🔗 Link received ✅",
            parse_mode="Markdown"
        )

        # ── Download Video ──
        response = requests.get(
            API_URL, params={"url": link},
            stream=True, timeout=300,
            headers={"User-Agent": "Mozilla/5.0"}
        )

        total_bytes = int(response.headers.get("content-length", 0))
        downloaded = 0
        last_percent = 0

        with open(filename, "wb") as f:
            for chunk in response.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_bytes > 0:
                        percent = int((downloaded / total_bytes) * 100)
                        if percent - last_percent >= 20:
                            last_percent = percent
                            filled = int(percent / 10)
                            bar = "🟩" * filled + "⬛" * (10 - filled)
                            try:
                                bot.edit_message_text(
                                    f"{prefix}"
                                    f"╔════════════════════╗\n"
                                    f"║   🎬 *VidBunker Bot*   ║\n"
                                    f"╚════════════════════╝\n\n"
                                    f"⏬ *Downloading...*\n\n"
                                    f"{bar}\n"
                                    f"📊 *{percent}%* — `{downloaded/1048576:.1f}MB / {total_bytes/1048576:.1f}MB`",
                                    message.chat.id, status.message_id,
                                    parse_mode="Markdown"
                                )
                            except:
                                pass

        actual_mb = os.path.getsize(filename) / (1024 * 1024)

        # ── Thumbnail Logic ──
        thumb_data = None

        if thumb_bytes:
            with open(thumb_file, "wb") as tf:
                tf.write(thumb_bytes)
            thumb_data = open(thumb_file, "rb")
        else:
            video_id = link.rstrip("/").split("/")[-1]
            thumb_urls = [
                f"https://vidbunker.in/thumbnails/{video_id}.jpg",
                f"https://vidbunker.in/thumbnail/{video_id}.jpg",
                f"https://vidbunker.in/uploads/thumbnails/{video_id}.jpg",
            ]
            for t_url in thumb_urls:
                try:
                    tr = requests.get(t_url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
                    if tr.status_code == 200 and len(tr.content) > 1000:
                        with open(thumb_file, "wb") as tf:
                            tf.write(tr.content)
                        thumb_data = open(thumb_file, "rb")
                        break
                except:
                    pass

        try:
            bot.edit_message_text(
                f"{prefix}"
                f"╔════════════════════╗\n"
                f"║   🎬 *VidBunker Bot*   ║\n"
                f"╚════════════════════╝\n\n"
                f"✅ *Download Complete!* `{actual_mb:.1f}MB`\n"
                f"📤 *Uploading to Telegram...*",
                message.chat.id, status.message_id,
                parse_mode="Markdown"
            )
        except:
            pass

        sent_msgs = []

        # ── Main Channel ──
        with open(filename, "rb") as vf:
            sent = bot.send_video(
                TARGET_GROUP_ID, vf,
                caption="",
                supports_streaming=True,
                thumbnail=thumb_data,
                width=1280, height=720,
                timeout=300
            )
            sent_msgs.append((TARGET_GROUP_ID, sent.message_id))

        # ── Forward Groups ──
        fwd_groups = get_forward_groups()
        for gid in fwd_groups:
            if gid != TARGET_GROUP_ID:
                try:
                    if thumb_data:
                        thumb_data.seek(0)
                    with open(filename, "rb") as vf:
                        s = bot.send_video(
                            gid, vf,
                            caption="",
                            supports_streaming=True,
                            thumbnail=thumb_data,
                            width=1280, height=720,
                            timeout=300
                        )
                        sent_msgs.append((gid, s.message_id))
                except Exception as e:
                    print(f"Forward error {gid}: {e}")

        # ── User ko bhejo ──
        if thumb_data:
            thumb_data.seek(0)
        with open(filename, "rb") as vf:
            bot.send_video(
                message.chat.id, vf,
                caption=(
                    f"╔════════════════════╗\n"
                    f"║   🎬 *VidBunker Bot*   ║\n"
                    f"╚════════════════════╝\n\n"
                    f"✅ *Successfully Downloaded!*\n\n"
                    f"📁 *Size:* `{actual_mb:.1f} MB`\n"
                    f"📡 *Forwarded to:* `{len(sent_msgs)} group(s)`\n"
                    f"🕐 *Time:* `{datetime.now().strftime('%d %b %Y, %I:%M %p')}`"
                ),
                supports_streaming=True,
                thumbnail=thumb_data,
                parse_mode="Markdown",
                width=1280, height=720,
                timeout=300,
                reply_to_message_id=message.message_id
            )

        # ── Cleanup ──
        if thumb_data:
            thumb_data.close()
        for f in [filename, thumb_file]:
            if os.path.exists(f):
                os.remove(f)

        try:
            bot.edit_message_text(
                f"╔════════════════════╗\n"
                f"║   ✅ *DONE!*            ║\n"
                f"╚════════════════════╝\n\n"
                f"🎬 Video successfully sent!\n"
                f"📁 Size: `{actual_mb:.1f} MB`\n"
                f"📡 Groups: `{len(sent_msgs)}`",
                message.chat.id, status.message_id,
                parse_mode="Markdown"
            )
        except:
            pass

        downloads_col.insert_one({
            "user_id": message.from_user.id,
            "username": message.from_user.username,
            "link": link,
            "size_mb": round(actual_mb, 2),
            "timestamp": datetime.now(),
            "forwarded_to": len(sent_msgs)
        })

    except Exception as e:
        try:
            bot.edit_message_text(
                f"╔════════════════════╗\n"
                f"║   ❌ *ERROR!*           ║\n"
                f"╚════════════════════╝\n\n"
                f"`{str(e)[:300]}`",
                message.chat.id, status.message_id,
                parse_mode="Markdown"
            )
        except:
            pass
        for f in [filename, thumb_file]:
            if os.path.exists(f):
                os.remove(f)

# ===== IMAGE + LINK HANDLER =====
pending_images = {}

@bot.message_handler(content_types=["photo"])
def handle_photo(message):
    save_user(message)
    file_id = message.photo[-1].file_id
    file_info = bot.get_file(file_id)
    photo_bytes = bot.download_file(file_info.file_path)

    pending_images[message.from_user.id] = {
        "bytes": photo_bytes,
        "time": time.time(),
        "msg_id": message.message_id
    }

    if message.caption and "vidbunker.in" in message.caption:
        links = [l.strip() for l in message.caption.split("\n") if "vidbunker.in" in l]
        del pending_images[message.from_user.id]
        for i, link in enumerate(links, 1):
            t = threading.Thread(
                target=process_video,
                args=(message, link, photo_bytes, i, len(links))
            )
            t.daemon = True
            t.start()
            time.sleep(0.5)
    else:
        bot.reply_to(
            message,
            "╔════════════════════╗\n"
            "║   📸 *Image Received!*  ║\n"
            "╚════════════════════╝\n\n"
            "✅ Image save ho gayi!\n"
            "🔗 Ab *Vidbunker link* bhejo — yahi image thumbnail banega!",
            parse_mode="Markdown"
        )

@bot.message_handler(func=lambda m: m.text and "vidbunker.in" in m.text)
def handle_link(message):
    save_user(message)
    lines = message.text.strip().split("\n")
    links = [l.strip() for l in lines if "vidbunker.in" in l]

    thumb_bytes = None
    uid = message.from_user.id
    if uid in pending_images:
        if time.time() - pending_images[uid]["time"] < 120:
            thumb_bytes = pending_images[uid]["bytes"]
        del pending_images[uid]

    if len(links) > 1:
        bot.reply_to(
            message,
            f"╔════════════════════╗\n"
            f"║   🎬 *Multiple Videos!*  ║\n"
            f"╚════════════════════╝\n\n"
            f"📋 *{len(links)} links mili hain*\n"
            f"⚙️ Processing shuru ho raha hai...",
            parse_mode="Markdown"
        )

    for i, link in enumerate(links, 1):
        t = threading.Thread(
            target=process_video,
            args=(message, link, thumb_bytes, i, len(links))
        )
        t.daemon = True
        t.start()
        time.sleep(0.5)

# ===== COMMANDS =====
@bot.message_handler(commands=["start"])
def start(message):
    save_user(message)
    total = downloads_col.count_documents({})
    users_count = users_col.count_documents({})
    bot.reply_to(
        message,
        f"╔══════════════════════╗\n"
        f"║  🎬 *VIDBUNKER BOT*  ║\n"
        f"║   *Download & Forward*   ║\n"
        f"╚══════════════════════╝\n\n"
        f"👋 *Welcome, {message.from_user.first_name}!*\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📥 *Total Downloads:* `{total}`\n"
        f"👥 *Total Users:* `{users_count}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📌 *How to Use:*\n\n"
        f"1️⃣ Sirf *Vidbunker link* bhejo\n"
        f"2️⃣ Pehle *image* bhejo, phir *link*\n"
        f"   _(Image thumbnail banega)_\n"
        f"3️⃣ *Image + caption* mein link\n"
        f"4️⃣ *Multiple links* — alag line mein\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ *Commands:*\n\n"
        f"📊 /stats — Bot statistics\n"
        f"📡 /groups — Forward groups\n"
        f"➕ /addgroup — Group add karo\n"
        f"📢 /broadcast — Sabko message\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🚀 *Ready! Link bhejo aur download shuru karo!*",
        parse_mode="Markdown"
    )

@bot.message_handler(commands=["stats"])
def stats(message):
    total = downloads_col.count_documents({})
    users = users_col.count_documents({})
    today = downloads_col.count_documents({
        "timestamp": {"$gte": datetime.now().replace(hour=0, minute=0, second=0)}
    })
    fwd = groups_col.count_documents({"active": True})
    bot.reply_to(
        message,
        f"╔════════════════════╗\n"
        f"║   📊 *BOT STATISTICS*   ║\n"
        f"╚════════════════════╝\n\n"
        f"📥 *Total Downloads:* `{total}`\n"
        f"👥 *Total Users:* `{users}`\n"
        f"📅 *Aaj ke Downloads:* `{today}`\n"
        f"📡 *Forward Groups:* `{fwd}`\n\n"
        f"🕐 `{datetime.now().strftime('%d %b %Y, %I:%M %p')}`",
        parse_mode="Markdown"
    )

@bot.message_handler(commands=["addgroup"])
def add_group(message):
    if not is_owner(message):
        return bot.reply_to(message, "❌ *Sirf owner use kar sakta hai!*", parse_mode="Markdown")
    try:
        parts = message.text.split()
        if len(parts) < 2:
            return bot.reply_to(
                message,
                "📌 *Usage:*\n`/addgroup -100xxxxxxxxx GroupName`",
                parse_mode="Markdown"
            )
        chat_id = int(parts[1])
        name = " ".join(parts[2:]) if len(parts) > 2 else "Unknown"
        groups_col.update_one(
            {"chat_id": chat_id},
            {"$set": {"chat_id": chat_id, "name": name, "active": True}},
            upsert=True
        )
        bot.reply_to(message, f"✅ *Group Added!*\n📌 Name: `{name}`\n🆔 ID: `{chat_id}`", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ *Error:* `{e}`", parse_mode="Markdown")

@bot.message_handler(commands=["removegroup"])
def remove_group(message):
    if not is_owner(message):
        return bot.reply_to(message, "❌ *Sirf owner use kar sakta hai!*", parse_mode="Markdown")
    parts = message.text.split()
    if len(parts) < 2:
        return bot.reply_to(message, "📌 *Usage:* `/removegroup -100xxxxxxxxx`", parse_mode="Markdown")
    chat_id = int(parts[1])
    groups_col.update_one({"chat_id": chat_id}, {"$set": {"active": False}})
    bot.reply_to(message, f"✅ *Group Removed:* `{chat_id}`", parse_mode="Markdown")

@bot.message_handler(commands=["groups"])
def list_groups(message):
    if not is_owner(message):
        return
    groups = list(groups_col.find({"active": True}))
    if not groups:
        return bot.reply_to(message, "❌ *Koi group nahi hai!*", parse_mode="Markdown")
    text = (
        f"╔════════════════════╗\n"
        f"║   📡 *FORWARD GROUPS*   ║\n"
        f"╚════════════════════╝\n\n"
    )
    for i, g in enumerate(groups, 1):
        text += f"{i}. *{g['name']}*\n   `{g['chat_id']}`\n\n"
    bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(commands=["broadcast"])
def broadcast(message):
    if not is_owner(message):
        return bot.reply_to(message, "❌ *Sirf owner use kar sakta hai!*", parse_mode="Markdown")
    text = message.text.replace("/broadcast", "").strip()
    if not text:
        return bot.reply_to(message, "📌 *Usage:* `/broadcast Aapka message`", parse_mode="Markdown")
    users = users_col.find({})
    sent = 0
    failed = 0
    for user in users:
        try:
            bot.send_message(
                user["user_id"],
                f"╔════════════════════╗\n"
                f"║   📢 *BROADCAST*        ║\n"
                f"╚════════════════════╝\n\n"
                f"{text}",
                parse_mode="Markdown"
            )
            sent += 1
        except:
            failed += 1
        time.sleep(0.05)
    bot.reply_to(message, f"✅ *Sent:* `{sent}`\n❌ *Failed:* `{failed}`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: True)
def unknown(message):
    bot.reply_to(
        message,
        "╔════════════════════╗\n"
        "║   ⚠️ *INVALID INPUT*    ║\n"
        "╚════════════════════╝\n\n"
        "🔗 *Vidbunker link* ya 📸 *image* bhejo!\n\n"
        "Help ke liye /start karo",
        parse_mode="Markdown"
    )

# ===== START =====
keep_alive()
print("✅ VidBunker Pro Bot chal raha hai...")
bot.infinity_polling(timeout=60, long_polling_timeout=30)
