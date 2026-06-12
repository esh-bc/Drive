import os
import re
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
DRIVE_API_KEY = os.environ.get("DRIVE_API_KEY")

import urllib.request
import json

def extract_folder_id(url):
    patterns = [
        r'/folders/([a-zA-Z0-9_-]+)',
        r'id=([a-zA-Z0-9_-]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def get_drive_files(folder_id):
    all_files = []
    page_token = None

    while True:
        url = (
            f"https://www.googleapis.com/drive/v3/files"
            f"?q=%27{folder_id}%27+in+parents+and+trashed%3Dfalse"
            f"&fields=nextPageToken,files(id,name,mimeType)"
            f"&pageSize=1000"
            f"&key={DRIVE_API_KEY}"
        )
        if page_token:
            url += f"&pageToken={page_token}"

        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())

        files = data.get("files", [])
        all_files.extend(files)

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    return all_files

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Send me a Google Drive folder link and I'll extract all file links for you!"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if "drive.google.com" not in text:
        await update.message.reply_text("❌ Please send a valid Google Drive folder link.")
        return

    folder_id = extract_folder_id(text)
    if not folder_id:
        await update.message.reply_text("❌ Couldn't extract folder ID from that link.")
        return

    await update.message.reply_text("⏳ Fetching files...")

    try:
        files = get_drive_files(folder_id)
    except Exception as e:
        logger.error(f"Drive API error: {e}")
        await update.message.reply_text(f"❌ Error fetching files: {str(e)}")
        return

    if not files:
        await update.message.reply_text("📂 Folder is empty or not accessible.")
        return

    # Filter out folders, keep files only
    only_files = [f for f in files if f.get("mimeType") != "application/vnd.google-apps.folder"]

    if not only_files:
        await update.message.reply_text("📂 No files found (only subfolders).")
        return

    first_file = only_files[0]["name"]
    total = len(only_files)

    # Store files in context for callback
    context.bot_data[folder_id] = only_files

    keyboard = [[InlineKeyboardButton("📋 Get All Links", callback_data=f"links:{folder_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"📁 *Folder Info*\n\n"
        f"📄 Total Files: *{total}*\n"
        f"🔹 First File: `{first_file}`",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    if not data.startswith("links:"):
        return

    folder_id = data.split(":", 1)[1]
    files = context.bot_data.get(folder_id)

    if not files:
        await query.message.reply_text("❌ Session expired. Please send the folder link again.")
        return

    links = []
    for f in files:
        file_id = f["id"]
        mime = f.get("mimeType", "")
        # Google Docs types get export links, others get direct links
        if "google-apps" in mime:
            link = f"https://drive.google.com/file/d/{file_id}/view"
        else:
            link = f"https://drive.google.com/uc?id={file_id}&export=download"
        links.append(link)

    all_links = "\n".join(links)

    # Telegram max message length is 4096
    if len(all_links) <= 4096:
        await query.message.reply_text(all_links)
    else:
        # Split into chunks
        chunk_size = 4000
        chunks = [all_links[i:i+chunk_size] for i in range(0, len(all_links), chunk_size)]
        for chunk in chunks:
            await query.message.reply_text(chunk)

def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN environment variable not set!")
    if not DRIVE_API_KEY:
        raise ValueError("DRIVE_API_KEY environment variable not set!")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback))

    logger.info("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
