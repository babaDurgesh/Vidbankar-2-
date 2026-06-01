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
BOT_TOKEN = os.environ.get("BOT_TOKEN")
FORWARD_CHAT_ID = os.environ.get("FORWARD_CHAT_ID")
VIDBUNKER_API = "https://vidbunker-backend.dailyweb577.workers.dev/api/download"
DOWNLOAD_DIR = "/tmp/downloads"
MAX_BATCH = 100
# ================================

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable nahi mila!")
if not FORWARD_CHAT_ID:
    raise ValueError("FORWARD_CHAT_ID environment variable nahi mila!")

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

user_queue: dict = {}


async def download_video(url: str, filename: str):
    try:
        async with aiohttp.ClientSession() as session:
            params = {"url": url}
            async with session.get(VIDBUNKER_API, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    logger.error(f"API error: {resp.status}")
                    return None
                data = await resp.json()

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


async def send_media_group(bot, chat_id, file_paths, caption=""):
    file_handles = []
    try:
        media = []
        for i, path in enumerate(file_paths[:10]):
            fh = open(path, 'rb')
            file_handles.append(fh)
            media.append(InputMediaVideo(
                media=fh,
                caption=caption if i == 0 else ""
            ))
        await bot.send_media_group(chat_id=chat_id, media=media)
        return True
    except TelegramError as e:
        logger.error(f"Media group error: {e}")
        return False
    finally:
        for fh in file_handles:
            fh.close()


async def process_and_forward(update: Update, context: ContextTypes.DEFAULT_TYPE, urls: list):
    bot = context.bot
    total = len(urls)
    status_msg = await update.message.reply_text(f"⏳ Processing {total} video(s)...\n0/{total} downloaded")

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
        await status_msg.edit_text("❌ Koi bhi video download nahi hua. URL check karo.")
        return

    await status_msg.edit_text(f"📤 Forwarding {len(downloaded)} videos...")

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
            for path in batch:
                try:
                    with open(path, 'rb') as f:
                        await bot.send_video(chat_id=FORWARD_CHAT_ID, video=f)
                    forwarded += 1
                except Exception as e:
                    logger.error(f"Send error: {e}")
        await asyncio.sleep(1)

    for path in downloaded:
        try:
            os.remove(path)
        except:
            pass

    await status_msg.edit_text(
        f"✅ Done!\n📤 Forwarded: {forwarded}/{total}\n❌ Failed: {failed}"
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *Video Downloader Bot*\n\n"
        "📌 *Commands:*\n"
        "/dl `<URL>` — Single video\n"
        "/batch — Batch mode shuru karo\n"
        "/send — Queue forward karo (max 100)\n"
        "/clear — Queue saaf karo\n"
        "/status — Queue dekho",
        parse_mode="Markdown"
    )


async def dl_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Usage: /dl <video_url>")
        return
    url = context.args[0]
    await process_and_forward(update, context, [url])


async def batch_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_queue[user_id] = []
    await update.message.reply_text(
        "📋 *Batch mode ON!*\n\nURLs bhejo (ek ek ya space se alag).\n/send se forward karo.\nMax: 100 URLs",
        parse_mode="Markdown"
    )


async def send_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    urls = user_queue.get(user_id, [])
    if not urls:
        await update.message.reply_text("❌ Queue empty! Pehle /batch mode mein URLs daalo.")
        return
    await update.message.reply_text(f"🚀 {len(urls)} videos process ho rahe hain...")
    user_queue[user_id] = []
    await process_and_forward(update, context, urls)


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    count = len(user_queue.get(user_id, []))
    user_queue[user_id] = []
    await update.message.reply_text(f"🗑️ {count} URLs remove kiye.")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    urls = user_queue.get(user_id, [])
    if not urls:
        await update.message.reply_text("📭 Queue empty hai.")
    else:
        url_list = "\n".join([f"{i+1}. {u[:50]}..." for i, u in enumerate(urls[:10])])
        more = f"\n...aur {len(urls)-10} aur" if len(urls) > 10 else ""
        await update.message.reply_text(f"📋 Queue: {len(urls)}/100\n\n{url_list}{more}", parse_mode="Markdown")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if user_id not in user_queue:
        await update.message.reply_text("💡 /batch mode mein URLs queue karo, ya /dl <url> se download karo.")
        return

    urls = [word for word in text.split() if word.startswith("http")]
    if not urls:
        await update.message.reply_text("❌ Valid URL nahi mila.")
        return

    current = user_queue[user_id]
    remaining = MAX_BATCH - len(current)
    if remaining <= 0:
        await update.message.reply_text(f"⚠️ Queue full! /send karo pehle.")
        return

    added = urls[:remaining]
    user_queue[user_id].extend(added)
    await update.message.reply_text(
        f"✅ {len(added)} URL(s) add hue.\n📋 Total: {len(user_queue[user_id])}/100\n/send se forward karo."
    )


def main():
    logger.info("Bot start ho raha hai...")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("dl", dl_command))
    app.add_handler(CommandHandler("batch", batch_command))
    app.add_handler(CommandHandler("send", send_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Bot chal raha hai!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
