from pyrogram import StopPropagation, enums, errors, filters, types

from KartikMusic import app, config

FSUB_CHANNEL = "SonicX_Robot"
FSUB_GROUP = "SonicXSupport"


async def is_not_joined(user_id: int):
    if user_id == config.OWNER_ID or user_id in app.sudoers:
        return []

    missing = []
    for chat in (FSUB_CHANNEL, FSUB_GROUP):
        try:
            member = await app.get_chat_member(chat, user_id)
            if member.status in (
                enums.ChatMemberStatus.LEFT,
                enums.ChatMemberStatus.BANNED,
            ):
                missing.append(chat)
        except errors.UserNotParticipant:
            missing.append(chat)
        except Exception:
            pass
    return missing


@app.on_message(filters.incoming & ~filters.bot & ~app.bl_users, group=-1)
async def force_sub_handler(_, m: types.Message):
    if not m.from_user:
        return

    if m.chat.type != enums.ChatType.PRIVATE:
        if not (m.text and m.text.startswith(("/", "!", "."))):
            return

    missing = await is_not_joined(m.from_user.id)
    if not missing:
        return

    buttons = []
    if FSUB_CHANNEL in missing:
        buttons.append(
            [
                types.InlineKeyboardButton(
                    text="📢 Join Updates Channel",
                    url=f"https://t.me/{FSUB_CHANNEL}",
                )
            ]
        )
    if FSUB_GROUP in missing:
        buttons.append(
            [
                types.InlineKeyboardButton(
                    text="💬 Join Support Group",
                    url=f"https://t.me/{FSUB_GROUP}",
                )
            ]
        )

    buttons.append(
        [
            types.InlineKeyboardButton(
                text="🔄 Try Again",
                url="https://t.me/TGSonicXbot?start=true",
            )
        ]
    )

    await m.reply_text(
        f"<blockquote><b><i>Hey {m.from_user.mention}! 👋\n\n"
        f"To use the bot, please join our Updates Channel and Support Group, then click Try Again! ❤️</i></b></blockquote>",
        reply_markup=types.InlineKeyboardMarkup(buttons),
        parse_mode=enums.ParseMode.HTML,
    )
    raise StopPropagation
