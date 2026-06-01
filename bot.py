import os
import asyncio
import aiohttp
import aiofiles
import logging
from telegram import Bot, InputMediaVideo
from telegram.error import TelegramError
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram import Update

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============ CONFIG ============
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
FORWARD_CHAT_ID = os.getenv("FORWARD_CHAT_ID", "YOUR_CHANNEL_OR_GROUP_ID")
VIDBUNKER_API = "https://vidbunker-backend.dailyweb577.workers.dev/api/download"
DOWNLOAD_DIR = "downloads"
MAX_BATCH = 100
# ================================

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Store pending URLs per user
user_queue: dict[int, list[str]] = {}


async def download_video(url: str, filename: str) -> str | None:
    """Download video using vidbunker API"""
    try:
        async with aiohttp.ClientSession() as session:
            # Call vidbunker API
            params = {"url": url}
            async with session.get(VIDBUNKER_API, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    logger.error(f"API error: {resp.status}")
                    return None
                data = await resp.json()

            # Get direct video URL from response
            video_url = (
                data.get("url") or
                data.get("download_url") or
                data.get("direct_url") or
                data.get("link") or
                (data.get("formats", [{}])[0].get("url") if data.get("formats") else None)
            )

            if not video_url:
                logger.error(f"No video URL in response: {data}")
                return None

            # Download the actual video file
            filepath = os.path.join(DOWNLOAD_DIR, filename)
            async with session.get(video_url, timeout=aiohttp.ClientTimeout(total=300)) as video_resp:
                if video_resp.status != 200:
                    return None
                async with aiofiles.open(filepath, 'wb') as f:
                    async for chunk in video_resp.content.iter_chunked(1024 * 1024):
                        await f.write(chunk)

            return filepath

    except Exception as e:
        logger.error(f"Download error: {e}")
        return None


async def send_media_group(bot: Bot, chat_id: str, file_paths: list[str], caption: str = "") -> bool:
    """Send up to 10 videos as media group"""
    try:
        media = []
        file_handles = []

        for i, path in enumerate(file_paths[:10]):
            fh = open(path, 'rb')
            file_handles.append(fh)
            media.append(InputMediaVideo(
                media=fh,
                caption=caption if i == 0 else ""
            ))

        await bot.send_media_group(chat_id=chat_id, media=media)

        for fh in file_handles:
            fh.close()
        return True

    except TelegramError as e:
        logger.error(f"Media group error: {e}")
        for fh in file_handles:
            fh.close()
        return False


async def process_and_forward(update: Update, context: ContextTypes.DEFAULT_TYPE, urls: list[str]):
    """Download all videos and forward in media groups of 10"""
    bot = context.bot
    total = len(urls)
    status_msg = await update.message.reply_text(
        f"⏳ Processing {total} video(s)...\n0/{total} downloaded"
    )

    downloaded = []
    failed = 0

    for i, url in enumerate(urls):
        await status_msg.edit_text(
            f"⬇️ Downloading {i+1}/{total}...\n"
            f"✅ Done: {len(downloaded)} | ❌ Failed: {failed}"
        )

        filename = f"video_{i+1}_{update.message.message_id}.mp4"
        filepath = await download_video(url, filename)

        if filepath:
            downloaded.append(filepath)
        else:
            failed += 1

    if not downloaded:
        await status_msg.edit_text("❌ Koi bhi video download nahi hua. URLs check karo.")
        return

    # Forward in batches of 10 (media group limit)
    await status_msg.edit_text(
        f"📤 Forwarding {len(downloaded)} videos to channel...\n"
        f"(Batches of 10)"
    )

    forwarded = 0
    batch_num = 0

    for i in range(0, len(downloaded), 10):
        batch = downloaded[i:i+10]
        batch_num += 1
        caption = f"📦 Batch {batch_num} | {forwarded+1}-{forwarded+len(batch)} of {len(downloaded)}"

        success = await send_media_group(bot, FORWARD_CHAT_ID, batch, caption)
        if success:
            forwarded += len(batch)
        else:
            # Try one by one if group fails
            for path in batch:
                try:
                    with open(path, 'rb') as f:
                        await bot.send_video(
                            chat_id=FORWARD_CHAT_ID,
                            video=f,
                            caption=f"Video {forwarded+1}/{len(downloaded)}"
                        )
                    forwarded += 1
                except Exception as e:
                    logger.error(f"Single video send error: {e}")

        await asyncio.sleep(1)  # Rate limit protection

    # Cleanup downloaded files
    for path in downloaded:
        try:
            os.remove(path)
        except:
            pass

    await status_msg.edit_text(
        f"✅ Done!\n"
        f"📤 Forwarded: {forwarded}/{total}\n"
        f"❌ Failed: {failed}\n"
        f"📍 Channel: {FORWARD_CHAT_ID}"
    )


# ============ COMMAND HANDLERS ============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *Video Downloader & Forwarder Bot*\n\n"
        "📌 *Commands:*\n"
        "/dl `<URL>` — Single video download & forward\n"
        "/batch — Batch mode (send URLs one by one, then /send)\n"
        "/send — Forward all queued URLs (max 100)\n"
        "/clear — Clear queue\n"
        "/status — Check queue\n\n"
        "🔗 Supported: YouTube, Instagram, TikTok, Facebook, etc.\n"
        "📦 Max batch: 100 videos",
        parse_mode="Markdown"
    )


async def dl_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Download single video: /dl <URL>"""
    if not context.args:
        await update.message.reply_text("❌ Usage: /dl <video_url>")
        return

    url = context.args[0]
    await process_and_forward(update, context, [url])


async def batch_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start batch mode"""
    user_id = update.effective_user.id
    user_queue[user_id] = []
    await update.message.reply_text(
        "📋 *Batch mode ON!*\n\n"
        "Ab video URLs bhejo (ek ek karke ya space se alag karke).\n"
        "Jab sab URLs dedo, /send likhke forward karo.\n"
        "Max: 100 URLs\n\n"
        "Queue clear karne ke liye: /clear",
        parse_mode="Markdown"
    )


async def send_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send all queued URLs"""
    user_id = update.effective_user.id
    urls = user_queue.get(user_id, [])

    if not urls:
        await update.message.reply_text("❌ Queue empty hai! Pehle /batch mode mein URLs daalo.")
        return

    await update.message.reply_text(f"🚀 Starting: {len(urls)} videos process ho rahe hain...")
    user_queue[user_id] = []
    await process_and_forward(update, context, urls)


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    count = len(user_queue.get(user_id, []))
    user_queue[user_id] = []
    await update.message.reply_text(f"🗑️ Queue cleared! {count} URLs remove kiye gaye.")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    urls = user_queue.get(user_id, [])
    if not urls:
        await update.message.reply_text("📭 Queue empty hai.")
    else:
        url_list = "\n".join([f"{i+1}. {u[:50]}..." for i, u in enumerate(urls[:10])])
        more = f"\n...aur {len(urls)-10} aur" if len(urls) > 10 else ""
        await update.message.reply_text(
            f"📋 *Queue Status:* {len(urls)}/100 URLs\n\n{url_list}{more}",
            parse_mode="Markdown"
        )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages - add URLs to queue if in batch mode"""
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if user_id not in user_queue:
        await update.message.reply_text(
            "💡 Tip: /batch mode mein URLs queue karo, ya /dl <url> se seedha download karo."
        )
        return

    # Extract URLs from message
    urls = [word for word in text.split() if word.startswith("http")]

    if not urls:
        await update.message.reply_text("❌ Koi valid URL nahi mila. http/https se shuru hona chahiye.")
        return

    current = user_queue[user_id]
    remaining = MAX_BATCH - len(current)

    if remaining <= 0:
        await update.message.reply_text(f"⚠️ Queue full hai! (Max {MAX_BATCH}). /send karo pehle.")
        return

    added = urls[:remaining]
    user_queue[user_id].extend(added)

    await update.message.reply_text(
        f"✅ {len(added)} URL(s) queue mein add hue.\n"
        f"📋 Total: {len(user_queue[user_id])}/100\n\n"
        f"Forward karne ke liye: /send"
    )


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("dl", dl_command))
    app.add_handler(CommandHandler("batch", batch_command))
    app.add_handler(CommandHandler("send", send_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot start ho gaya!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
