import os
import re
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CopyTextButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN  = os.environ.get("BOT_TOKEN")
DRIVE_API_KEY = os.environ.get("DRIVE_API_KEY")

import urllib.request
import json

# ══════════════════════════════════════════
#   HELPERS
# ══════════════════════════════════════════

def extract_folder_id(url: str):
    patterns = [
        r'/folders/([a-zA-Z0-9_-]+)',
        r'id=([a-zA-Z0-9_-]+)',
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def get_drive_files(folder_id: str):
    all_files  = []
    page_token = None
    while True:
        url = (
            f"https://www.googleapis.com/drive/v3/files"
            f"?q=%27{folder_id}%27+in+parents+and+trashed%3Dfalse"
            f"&fields=nextPageToken,files(id,name,mimeType,size)"
            f"&pageSize=1000"
            f"&key={DRIVE_API_KEY}"
        )
        if page_token:
            url += f"&pageToken={page_token}"
        with urllib.request.urlopen(urllib.request.Request(url)) as r:
            data = json.loads(r.read().decode())
        all_files.extend(data.get("files", []))
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return all_files


def make_link(file_id: str) -> str:
    return f"https://drive.google.com/file/d/{file_id}/view?usp=drivesdk"


def fmt_size(s) -> str:
    try:
        n = int(s)
        if n >= 1_073_741_824: return f"{n/1_073_741_824:.1f} GB"
        if n >= 1_048_576:     return f"{n/1_048_576:.1f} MB"
        if n >= 1_024:         return f"{n/1_024:.1f} KB"
        return f"{n} B"
    except (TypeError, ValueError):
        return "—"


MAX_PER_PAGE = 25   # links shown per page

# ══════════════════════════════════════════
#   /start  &  /help
# ══════════════════════════════════════════

WELCOME = (
    "╔══════════════════════╗\n"
    "   \U0001f5c2  Drive Link Extractor  \n"
    "╚══════════════════════╝\n\n"
    "*Send me a Google Drive folder link*\n"
    "and I will extract every file link for you!\n\n"
    "\u25b6 Each link is in mono \u2192 tap once to copy\n"
    "\u25b6 One button copies ALL links at once\n"
    "\u25b6 Paginated for huge folders\n\n"
    "Paste your folder link below \u2193"
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [
            InlineKeyboardButton("\u2139 How to Use",   callback_data="help",  style="primary"),
            InlineKeyboardButton("\u2606 About",        callback_data="about", style="success"),
        ]
    ]
    await update.message.reply_text(
        WELCOME, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "help":
        text = (
            "\u2139 *How to Use*\n\n"
            "1\ufe0f\u20e3  Open Google Drive\n"
            "2\ufe0f\u20e3  Right-click folder \u2192 Share \u2192 Copy link\n"
            "3\ufe0f\u20e3  Paste the link here\n"
            "4\ufe0f\u20e3  Tap *Get All Links*\n"
            "5\ufe0f\u20e3  Tap any `link` to copy it\n"
            "      OR tap *Copy All* for everything!\n\n"
            "\u26a0 Folder must be publicly shared\n"
            "   or accessible via your API key."
        )
    else:
        text = (
            "\u2606 *About This Bot*\n\n"
            "Google Drive Link Extractor\n"
            "Powered by Drive API v3\n\n"
            "Link format:\n"
            "`https://drive.google.com/file/d/<id>`\n"
            "`/view?usp=drivesdk`\n\n"
            "Built with python-telegram-bot v22.7+"
        )

    kb = [[InlineKeyboardButton("\u2190 Back", callback_data="back_start", style="primary")]]
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def back_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    kb = [
        [
            InlineKeyboardButton("\u2139 How to Use", callback_data="help",  style="primary"),
            InlineKeyboardButton("\u2606 About",      callback_data="about", style="success"),
        ]
    ]
    await q.edit_message_text(WELCOME, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


# ══════════════════════════════════════════
#   FOLDER LINK  \u2192  FOLDER INFO
# ══════════════════════════════════════════

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if "drive.google.com" not in text:
        await update.message.reply_text(
            "\u2716 Please send a valid *Google Drive folder link*.",
            parse_mode="Markdown",
        )
        return

    folder_id = extract_folder_id(text)
    if not folder_id:
        await update.message.reply_text(
            "\u2716 Could not extract folder ID.\n"
            "Make sure it is a shared folder URL!",
            parse_mode="Markdown",
        )
        return

    wait = await update.message.reply_text("\u29d6 Fetching files\u2026 please wait!")

    try:
        files = get_drive_files(folder_id)
    except Exception as e:
        logger.error(f"Drive API error: {e}")
        await wait.edit_text(f"\u2716 Drive API error:\n`{e}`", parse_mode="Markdown")
        return

    await wait.delete()

    only_files  = [f for f in files if f.get("mimeType") != "application/vnd.google-apps.folder"]
    subfolders  = [f for f in files if f.get("mimeType") == "application/vnd.google-apps.folder"]

    if not only_files:
        note = " (has sub-folders)" if subfolders else ""
        await update.message.reply_text(f"\u25a1 Folder is empty{note}. No direct files found.")
        return

    total          = len(only_files)
    all_links_str  = "\n".join(make_link(f["id"]) for f in only_files)

    # Store for callbacks
    context.bot_data[folder_id] = only_files

    kb = [
        [
            InlineKeyboardButton(
                f"\u25b6 Get All Links  ({total})",
                callback_data=f"links:{folder_id}:0",
                style="success",            # green
            ),
        ],
        [
            # CopyTextButton = 1-tap copies ALL links to clipboard
            InlineKeyboardButton(
                f"\u29c9 Copy All {total} Links",
                copy_text=CopyTextButton(text=all_links_str),
                style="primary",            # blue
            ),
        ],
        [
            InlineKeyboardButton(
                "\u2715 Clear Session",
                callback_data=f"clear:{folder_id}",
                style="danger",             # red
            ),
        ],
    ]

    await update.message.reply_text(
        f"\u250c{'─'*26}\u2510\n"
        f"\u2502   \U0001f5c1  Folder Ready!{'':12}\u2502\n"
        f"\u2514{'─'*26}\u2518\n\n"
        f"*Total Files:*  `{total}`\n"
        f"*Sub-folders:*  `{len(subfolders)}`\n"
        f"*First File:*\n"
        f"`{only_files[0]['name']}`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb),
    )


# ══════════════════════════════════════════
#   LINKS PAGE CALLBACK
# ══════════════════════════════════════════

async def links_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data

    # ── clear ──────────────────────────────────────────────────────
    if data.startswith("clear:"):
        fid = data.split(":", 1)[1]
        context.bot_data.pop(fid, None)
        await q.edit_message_text("\u2713 Session cleared. Send another folder link anytime!")
        return

    # ── links:<folder_id>:<page> ───────────────────────────────────
    parts     = data.split(":")
    folder_id = parts[1]
    page      = int(parts[2]) if len(parts) > 2 else 0

    files = context.bot_data.get(folder_id)
    if not files:
        await q.message.reply_text("\u2716 Session expired. Please resend the folder link.")
        return

    total       = len(files)
    total_pages = (total + MAX_PER_PAGE - 1) // MAX_PER_PAGE
    start_i     = page * MAX_PER_PAGE
    end_i       = min(start_i + MAX_PER_PAGE, total)
    page_files  = files[start_i:end_i]

    # Build message — links in monospace (tap = copy on mobile)
    lines = []
    for idx, f in enumerate(page_files, start=start_i + 1):
        link = make_link(f["id"])
        name = f["name"]
        size = fmt_size(f.get("size"))
        lines.append(
            f"*{idx}.* `{name}`\n"
            f"     `{link}`\n"
            f"     {size}"
        )

    header = (
        f"\u250c{'─'*26}\u2510\n"
        f"\u2502  Page {page+1} / {total_pages}  \u2022  Files {start_i+1}\u2013{end_i} of {total}\n"
        f"\u2514{'─'*26}\u2518\n\n"
    )
    body = "\n\n".join(lines)
    full = header + body

    # Per-page and all-links copy strings
    page_links_str = "\n".join(make_link(f["id"]) for f in page_files)
    all_links_str  = "\n".join(make_link(f["id"]) for f in files)

    # Navigation row
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(
            "\u2190 Prev", callback_data=f"links:{folder_id}:{page-1}", style="primary"
        ))
    if end_i < total:
        nav.append(InlineKeyboardButton(
            "Next \u2192", callback_data=f"links:{folder_id}:{page+1}", style="primary"
        ))

    kb = []
    if nav:
        kb.append(nav)
    kb.append([
        InlineKeyboardButton(
            f"\u29c9 Copy Page ({len(page_files)} links)",
            copy_text=CopyTextButton(text=page_links_str),
            style="success",      # green
        ),
    ])
    kb.append([
        InlineKeyboardButton(
            f"\u29c9 Copy ALL {total} Links",
            copy_text=CopyTextButton(text=all_links_str),
            style="primary",      # blue
        ),
    ])
    kb.append([
        InlineKeyboardButton(
            "\u2190 Back to Folder Info",
            callback_data=f"back_info:{folder_id}",
            style="danger",       # red
        ),
    ])

    # Send — split if over Telegram's 4096 char limit
    if len(full) <= 4096:
        await q.message.reply_text(
            full, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(kb),
        )
    else:
        chunks = [full[i:i+3800] for i in range(0, len(full), 3800)]
        for ci, chunk in enumerate(chunks):
            if ci == len(chunks) - 1:
                await q.message.reply_text(
                    chunk, parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(kb),
                )
            else:
                await q.message.reply_text(chunk, parse_mode="Markdown")


async def back_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Re-show the folder info card."""
    q = update.callback_query
    await q.answer()
    folder_id = q.data.split(":", 1)[1]
    files = context.bot_data.get(folder_id)
    if not files:
        await q.message.reply_text("\u2716 Session expired. Please resend the folder link.")
        return

    total         = len(files)
    all_links_str = "\n".join(make_link(f["id"]) for f in files)
    kb = [
        [
            InlineKeyboardButton(
                f"\u25b6 Get All Links  ({total})",
                callback_data=f"links:{folder_id}:0",
                style="success",
            ),
        ],
        [
            InlineKeyboardButton(
                f"\u29c9 Copy All {total} Links",
                copy_text=CopyTextButton(text=all_links_str),
                style="primary",
            ),
        ],
        [
            InlineKeyboardButton(
                "\u2715 Clear Session",
                callback_data=f"clear:{folder_id}",
                style="danger",
            ),
        ],
    ]
    await q.message.reply_text(
        f"\u250c{'─'*26}\u2510\n"
        f"\u2502   \U0001f5c1  Folder Ready!{'':12}\u2502\n"
        f"\u2514{'─'*26}\u2518\n\n"
        f"*Total Files:*  `{total}`\n"
        f"*First File:*\n"
        f"`{files[0]['name']}`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb),
    )


# ══════════════════════════════════════════
#   MAIN
# ══════════════════════════════════════════

def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN environment variable is not set!")
    if not DRIVE_API_KEY:
        raise ValueError("DRIVE_API_KEY environment variable is not set!")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help",  start))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.add_handler(CallbackQueryHandler(info_callback,      pattern="^(help|about)$"))
    app.add_handler(CallbackQueryHandler(back_start_callback, pattern="^back_start$"))
    app.add_handler(CallbackQueryHandler(links_callback,     pattern="^(links:|clear:)"))
    app.add_handler(CallbackQueryHandler(back_info_callback, pattern="^back_info:"))

    logger.info("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
