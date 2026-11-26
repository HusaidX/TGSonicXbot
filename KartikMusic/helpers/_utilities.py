# All rights reserved.


from datetime import datetime
from html import escape
import re
from zoneinfo import ZoneInfo

from pyrogram import enums, types
from pyrogram.errors import FloodWait, RPCError

from KartikMusic import app


class Utilities:
    def __init__(self):
        pass

    def format_eta(self, seconds: int) -> str:
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            return f"{seconds // 60}:{seconds % 60:02d} min"
        else:
            h = seconds // 3600
            m = (seconds % 3600) // 60
            s = seconds % 60
            return f"{h}:{m:02d}:{s:02d} h"

    def format_size(self, bytes: int) -> str:
        if bytes >= 1024**3:
            return f"{bytes / 1024**3:.2f} GB"
        elif bytes >= 1024**2:
            return f"{bytes / 1024**2:.2f} MB"
        else:
            return f"{bytes / 1024:.2f} KB"

    def to_seconds(self, time: str) -> int:
        parts = [int(p) for p in time.strip().split(":")]
        return sum(value * 60**i for i, value in enumerate(reversed(parts)))

    def get_url(self, message_1: types.Message) -> str | None:
        link = None
        messages = [message_1]

        if message_1.reply_to_message:
            messages.append(message_1.reply_to_message)

        for message in messages:
            entities = message.entities or message.caption_entities or []

            for entity in entities:
                if entity.type == enums.MessageEntityType.TEXT_LINK:
                    link = entity.url
                    break
                elif entity.type == enums.MessageEntityType.URL:
                    text = message.text or message.caption
                    if not text:
                        continue
                    link = text[entity.offset : entity.offset + entity.length]
                    break

        if link:
            return link.split("&si")[0].split("?si")[0]
        return None

    async def extract_user(self, msg: types.Message) -> types.User | None:
        if msg.reply_to_message:
            return msg.reply_to_message.from_user

        if msg.entities:
            for e in msg.entities:
                if e.type == enums.MessageEntityType.TEXT_MENTION:
                    return e.user

        if msg.text:
            try:
                if m := re.search(r"@(\w{5,32})", msg.text):
                    return await app.get_users(m.group(0))
                if m := re.search(r"\b\d{6,15}\b", msg.text):
                    return await app.get_users(int(m.group(0)))
            except Exception:
                pass

        return None

    async def play_log(
        self,
        m: types.Message,
        link: str,
        title: str,
        duration: str,
    ) -> None:
        if m.chat.id == app.logger:
            return
        _text = m.lang["play_log"].format(
            app.name,
            m.chat.id,
            m.chat.title,
            m.from_user.id,
            m.from_user.mention,
            link,
            title,
            duration,
        )
        await app.send_message(chat_id=app.logger, text=_text)

    async def send_log(
        self,
        m: types.Message,
        chat: bool = False,
        start_count: int = 1,
        bio: str | None = None,
    ) -> None:
        if not getattr(app, "logger", None):
            return

        if chat:
            user = m.from_user
            return await app.send_message(
                chat_id=app.logger,
                text=m.lang["log_chat"].format(
                    m.chat.id,
                    m.chat.title,
                    user.id if user else 0,
                    user.mention if user else "Anonymous",
                ),
            )

        user = m.from_user
        if not user:
            return

        full_name = escape(
            f"{user.first_name or ''} {user.last_name or ''}".strip() or "Unknown"
        )
        username_text = escape(f"@{user.username}") if user.username else "None"
        phone_text = (
            escape(m.contact.phone_number)
            if getattr(m, "contact", None) and m.contact.phone_number
            else "Not Shared"
        )
        bio_text = escape(bio) if bio else "Not Set"
        premium_text = "Yes" if user.is_premium else "No"
        lang_text = escape((user.language_code or "Unknown").upper())
        dc_text = str(user.dc_id) if user.dc_id else "Unknown"
        ist_time = datetime.now(ZoneInfo("Asia/Kolkata")).strftime(
            "%d %b %Y, %I:%M:%S %p IST"
        )

        _text = (
            "🆕 <b>User Started Bot</b>\n\n"
            f"👤 <b>Name:</b> {full_name}\n"
            f"🆔 <b>User ID:</b> <code>{user.id}</code>\n"
            f"🔗 <b>Username:</b> {username_text}\n"
            f"📞 <b>Phone Number:</b> {phone_text}\n"
            f"📝 <b>Bio:</b> {bio_text}\n"
            f"⭐ <b>Premium:</b> {premium_text} | 🌐 <b>Lang:</b> {lang_text} | 📡 <b>DC:</b> {dc_text}\n"
            f"🔁 <b>Start Count:</b> {start_count}\n"
            f"🕒 <b>Time:</b> {ist_time}"
        )

        try:
            await app.send_message(
                chat_id=app.logger,
                text=_text,
                parse_mode=enums.ParseMode.HTML,
            )
        except (FloodWait, RPCError, Exception):
            pass
