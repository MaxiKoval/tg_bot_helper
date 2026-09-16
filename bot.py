import logging
import asyncio
from datetime import datetime
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
        "Привет! Отправь мне фото или файл — я загружу его на GitHub в папку covers "
        "под исходным именем и верну ссылку."
    )


async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    await msg.chat.send_action(ChatAction.UPLOAD_PHOTO)
    tg_file = await msg.photo[-1].get_file()
    content = bytes(await tg_file.download_as_bytearray())

    # У фото из Telegram нет имени — генерируем по дате-времени
    filename = f"photo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    await _process_and_reply(msg, content, filename)


async def handle_document(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc.mime_type or not doc.mime_type.startswith("image/"):
        await update.message.reply_text("Это не изображение 🤔")
        return

    await update.message.chat.send_action(ChatAction.UPLOAD_PHOTO)
    tg_file = await doc.get_file()
    content = bytes(await tg_file.download_as_bytearray())

    # У документа есть исходное имя — используем его
    filename = doc.file_name or f"file_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    await _process_and_reply(update.message, content, filename)


async def _process_and_reply(msg, content: bytes, filename: str):
    try:
        result = await asyncio.to_thread(upload_image, content, filename)
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
