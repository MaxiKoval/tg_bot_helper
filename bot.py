import logging
import asyncio
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters,
)
from config import TELEGRAM_TOKEN
from github_uploader import upload_image

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Отправь мне фото — я загружу его на GitHub и верну ссылку."
    )


async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    await msg.chat.send_action(ChatAction.UPLOAD_PHOTO)
    tg_file = await msg.photo[-1].get_file()
    content = bytes(await tg_file.download_as_bytearray())
    await _process_and_reply(msg, content, "jpg")


async def handle_document(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc.mime_type or not doc.mime_type.startswith("image/"):
        await update.message.reply_text("Это не изображение 🤔")
        return
    await update.message.chat.send_action(ChatAction.UPLOAD_PHOTO)
    tg_file = await doc.get_file()
    content = bytes(await tg_file.download_as_bytearray())
    ext = "jpg"
    if "." in doc.file_name:
        ext = doc.file_name.rsplit(".", 1)[-1].lower()
    await _process_and_reply(update.message, content, ext)


async def _process_and_reply(msg, content: bytes, ext: str):
    try:
        result = await asyncio.to_thread(upload_image, content, ext)
    except Exception as e:
        log.exception("Upload failed")
        await msg.reply_text(f"❌ Ошибка загрузки: {e}")
        return

    lines = [
        "✅ Загружено на GitHub",
        "",
        f"📁 <code>{result['path']}</code>",
        "",
        "🔗 Ссылки:",
    ]
    if result.get("cdn_url"):
        lines.append(f"• <a href=\"{result['cdn_url']}\">CDN (jsDelivr)</a>")
    lines.append(f"• <a href=\"{result['raw_url']}\">raw.githubusercontent</a>")

    await msg.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.IMAGE, handle_document))
    log.info("Bot started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
