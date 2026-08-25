"""
Telegram-integration.

Skickar en graf-bild med bildtext till en Telegram-chatt via
python-telegram-bot. Kräver TELEGRAM_BOT_TOKEN och TELEGRAM_CHAT_ID
(se .env.example och SETUP_GUIDE.md för hur du skapar dessa).
"""
import asyncio

from telegram import Bot
from telegram.constants import ParseMode

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


async def _send_photo_async(photo_path: str, caption: str) -> None:
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    with open(photo_path, "rb") as f:
        await bot.send_photo(
            chat_id=TELEGRAM_CHAT_ID,
            photo=f,
            caption=caption,
            parse_mode=ParseMode.MARKDOWN,
        )


def send_photo(photo_path: str, caption: str) -> None:
    """
    Skickar en bild med bildtext till Telegram. Skriver bara en varning
    till konsollen (skickar inget) om token/chat_id saknas, så scriptet
    fortfarande går att testköra utan Telegram konfigurerat.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[VARNING] TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID är inte satta - skickar inget till Telegram.")
        print("--- Caption som skulle skickats ---")
        print(caption)
        return

    asyncio.run(_send_photo_async(photo_path, caption))


async def _send_message_async(text: str) -> None:
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text)


def send_test_message() -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[FEL] TELEGRAM_BOT_TOKEN och/eller TELEGRAM_CHAT_ID är inte satta i .env")
        return
    asyncio.run(_send_message_async("Telegram-anslutning OK! Aktiescannen är korrekt konfigurerad."))
    print("[OK] Testmeddelande skickat till Telegram.")
