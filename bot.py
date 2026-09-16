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
from github_uploader import upload_image, upload_zip

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

_bot_messages = []


async def _reply(msg, text: str, **kwargs):
    sent = await msg.reply_text(text, **kwargs)
    try:
        _bot_messages.append(sent.message_id)
    except Exception:
        pass
    return sent


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await _reply(
        update.message,
        "Привет! Я умею:\n"
        "• 📷 Загружать фото\n"
        "• 📎 Загружать файлы (с именем)\n"
        "• 📦 Распаковывать ZIP-архивы с картинками\n\n"
        "💡 Добавь подпись к фото = название игры. "
        "Например, <b>Among Us</b> → фото уйдёт в <code>covers/a1</code> "
        "(первая буква). Когда в папке наберётся 500 фото — создастся <code>a2</code>.\n\n"
        "Команды:\n"
        "/clear — удалить сообщения бота из чата",
        parse_mode="HTML",
    )


async def clear(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    deleted, failed = 0, 0
    for mid in list(_bot_messages):
        try:
            await ctx.bot.delete_message(chat_id=chat_id, message_id=mid)
            deleted += 1
        except Exception:
            failed += 1
    _bot_messages.clear()

    sent = await ctx.bot.send_message(
        chat_id=chat_id,
        text=(
            f"🧹 Удалено сообщений бота: {deleted}\n"
            + (f"⚠️ Не удалось: {failed} (старше 48 часов)\n" if failed else "")
            + "\n⚠️ Telegram Bot API <b>не даёт</b> боту удалять ваши "
            "сообщения и файлы. Чтобы стереть всё — откройте меню чата (⋮) → "
            "<b>Clear history</b>."
        ),
        parse_mode="HTML",
    )
    _bot_messages.append(sent.message_id)


async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    await msg.chat.send_action(ChatAction.UPLOAD_PHOTO)
    tg_file = await msg.photo[-1].get_file()
    content = bytes(await tg_file.download_as_bytearray())

    filename = f"photo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    game_name = (msg.caption or "").strip()
    await _process_and_reply(msg, content, filename, game_name)


async def handle_document(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    fname = (doc.file_name or "").lower()

    if fname.endswith(".zip"):
        await _handle_zip(update, ctx)
        return

    if not doc.mime_type or not doc.mime_type.startswith("image/"):
        await _reply(update.message, "Принимаю только изображения и ZIP-архивы 🤔")
        return

    await update.message.chat.send_action(ChatAction.UPLOAD_PHOTO)
    tg_file = await doc.get_file()
    content = bytes(await tg_file.download_as_bytearray())

    filename = doc.file_name or f"file_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    game_name = (update.message.caption or "").strip()
    await _process_and_reply(update.message, content, filename, game_name)


async def _handle_zip(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    doc = msg.document

    if doc.file_size and doc.file_size > 20 * 1024 * 1024:
        await _reply(
            msg,
            "⚠️ Файл больше 20 МБ. Telegram Bot API не отдаёт такие файлы ботам.",
        )
        return

    game_name = (msg.caption or "").strip()
    await _reply(msg, f"📦 Принял {doc.file_name}, распаковываю…")
    await msg.chat.send_action(ChatAction.UPLOAD_DOCUMENT)

    try:
        tg_file = await doc.get_file()
        content = bytes(await tg_file.download_as_bytearray())
    except Exception as e:
        log.exception("Download failed")
        await _reply(msg, f"❌ Не удалось скачать файл: {e}")
        return

    try:
        result = await asyncio.to_thread(upload_zip, content, doc.file_name, game_name)
    except Exception as e:
        log.exception("Zip upload failed")
        await _reply(msg, f"❌ Ошибка: {e}")
        return

    uploaded = result["uploaded"]
    skipped = result["skipped"]
    failed = result["failed"]

    lines = [f"✅ Загружено файлов: <b>{len(uploaded)}</b>"]
    if skipped:
        lines.append(f"⏭ Пропущено: {len(skipped)}")
    if failed:
        lines.append(f"❌ Ошибок: {len(failed)}")
    if uploaded:
        lines.append("")
        lines.append("📁 Первые файлы:")
        for p in uploaded[:10]:
            lines.append(f"• <code>{p}</code>")
        if len(uploaded) > 10:
            lines.append(f"…и ещё {len(uploaded) - 10}")
    if result.get("note"):
        lines.append("")
        lines.append(f"ℹ️ {result['note']}")

    await _reply(msg, "\n".join(lines), parse_mode="HTML",
                 disable_web_page_preview=True)


async def _process_and_reply(msg, content: bytes, filename: str, game_name: str = ""):
    try:
        result = await asyncio.to_thread(upload_image, content, filename, game_name)
    except Exception as e:
        log.exception("Upload failed")
        await _reply(msg, f"❌ Ошибка загрузки: {e}")
        return

    lines = [
        "✅ Загружено на GitHub",
        "",
        f"📁 <code>{result['path']}</code>",
        "",
        "🔗 Ссылки:",
    ]
    if result.get("cdn_url"):
        lines.append(f'• <a href="{result["cdn_url"]}">CDN (jsDelivr)</a>')
    lines.append(f'• <a href="{result["raw_url"]}">raw.githubusercontent</a>')

    await _reply(msg, "\n".join(lines), parse_mode="HTML",
                 disable_web_page_preview=True)


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    log.info("Bot started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
