import re
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot.database import Database
from bot.config import config
from bot.keyboards.inline import get_api_keys_keyboard

router = Router(name="admin_router")


class AdminStates(StatesGroup):
    waiting_for_bulk_keys = State()


def is_admin(user_id: int) -> bool:
    if not config.ADMIN_IDS:
        return True
    return user_id in config.ADMIN_IDS


@router.message(Command("stats"))
async def cmd_stats(message: types.Message, db: Database):
    user_id = message.from_user.id
    user_stats = await db.get_user_stats(user_id)
    queue_stats = await db.get_queue_stats()
    key_stats = await db.get_sorsa_keys_stats()

    is_adm = is_admin(user_id)

    text = (
        "📊 <b>Engagement Bot Statistics</b>\n\n"
        "👤 <b>Your Stats:</b>\n"
        f"• Posts Submitted: <b>{user_stats['total_submitted']}</b>\n"
        f"• Posts Fully Verified: <b>{user_stats['total_verified']}</b>\n"
        f"• Comments You Verified: <b>{user_stats['total_comments_done']}</b>\n\n"
        "🌐 <b>Global Pool Stats:</b>\n"
        f"• Total Registered Users: <b>{queue_stats['total_users']}</b>\n"
        f"• Total Posts in Queue: <b>{queue_stats['total_posts']}</b>\n"
        f"• Total Verified Engagements: <b>{queue_stats['verified_engagements']}</b>\n\n"
        "🔑 <b>Sorsa API Keys Status:</b>\n"
        f"• Active Keys: <b>{key_stats['active']}</b>\n"
        f"• Rate-Limited / Exhausted: <b>{key_stats['rate_limited']}</b>\n"
        f"• Invalid Keys: <b>{key_stats['invalid']}</b>\n"
        f"• Total In Pool: <b>{key_stats['total']}</b>\n"
    )

    if is_adm:
        text += "\n🛡️ <i>You are recognized as a Bot Administrator. Use /keys to manage API keys.</i>"

    await message.answer(text, parse_mode="HTML")


@router.message(Command("keys", "apikeys"))
async def cmd_keys(message: types.Message, db: Database):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Access restricted to administrators.")
        return

    stats = await db.get_sorsa_keys_stats()
    text = (
        "🔑 <b>Sorsa API Key Pool Management</b>\n\n"
        f"• 🟢 <b>Active Keys:</b> {stats['active']}\n"
        f"• 🟡 <b>Rate-Limited / Exhausted:</b> {stats['rate_limited']}\n"
        f"• 🔴 <b>Invalid Keys:</b> {stats['invalid']}\n"
        f"• 📁 <b>Total Keys in Pool:</b> {stats['total']}\n\n"
        "💡 <i>You can paste bulk keys below or use:</i>\n"
        "• <code>/addkeys key1 key2 key3 ...</code>\n"
        "• <code>/resetkeys</code> - Reactivate all rate-limited keys\n"
        "• <code>/delkey &lt;key&gt;</code> - Remove a specific key"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_api_keys_keyboard())


@router.message(Command("addkeys", "addkey"))
async def cmd_addkeys(message: types.Message, db: Database):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Access restricted to administrators.")
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "⚠️ Please provide one or more Sorsa API keys.\n\n"
            "Example:\n<code>/addkey your_sorsa_api_key</code>\n"
            "<i>(You can also paste multiple keys separated by spaces, commas, or newlines)</i>",
            parse_mode="HTML"
        )
        return

    raw_input = args[1]
    keys = [k.strip() for k in re.split(r"[\r\n,;\s]+", raw_input) if k.strip()]
    if not keys:
        await message.answer("❌ No valid keys detected in your message.")
        return

    added, duplicates = await db.add_sorsa_keys(keys)
    await message.answer(
        f"✅ <b>Sorsa Key(s) Processed:</b>\n"
        f"• Added: <b>{added}</b> new keys\n"
        f"• Already in Pool: <b>{duplicates}</b> duplicate(s)\n\n"
        f"Use /keys to view pool status.",
        parse_mode="HTML"
    )


@router.message(Command("delinactive", "deldeadkeys"))
async def cmd_del_inactive(message: types.Message, db: Database):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Access restricted to administrators.")
        return

    deleted = await db.delete_inactive_sorsa_keys()
    await message.answer(
        f"🗑️ Successfully deleted <b>{deleted}</b> inactive / rate-limited / invalid key(s) from the pool!",
        parse_mode="HTML"
    )


@router.message(Command("resetkeys"))
async def cmd_resetkeys(message: types.Message, db: Database):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Access restricted to administrators.")
        return

    count = await db.reset_all_sorsa_keys()
    await message.answer(f"🔄 Reactivated <b>{count}</b> Sorsa API key(s) back to active status!", parse_mode="HTML")


@router.message(Command("delkey"))
async def cmd_delkey(message: types.Message, db: Database):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Access restricted to administrators.")
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("⚠️ Usage: <code>/delkey &lt;api_key&gt;</code>", parse_mode="HTML")
        return

    key = args[1].strip()
    removed = await db.remove_sorsa_key(key)
    if removed:
        await message.answer("🗑️ Sorsa API key successfully removed from pool.")
    else:
        await message.answer("⚠️ Key not found in pool.")


# Interactive Callbacks for Keys Management
@router.callback_query(F.data == "prompt_add_keys")
async def cb_prompt_add_keys(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Access restricted.", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_for_bulk_keys)
    await callback.message.answer(
        "📥 <b>Paste Bulk Sorsa API Keys:</b>\n\n"
        "Send your Sorsa API keys now. You can paste multiple keys separated by newlines, spaces, or commas.\n\n"
        "<i>Send /cancel to abort.</i>",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminStates.waiting_for_bulk_keys)
async def state_receive_bulk_keys(message: types.Message, state: FSMContext, db: Database):
    if message.text.strip().lower() == "/cancel":
        await state.clear()
        await message.answer("Cancelled bulk key addition.")
        return

    keys = [k.strip() for k in re.split(r"[\r\n,;\s]+", message.text) if k.strip()]
    if not keys:
        await message.answer("❌ No valid keys detected. Please paste one or more keys or type /cancel:")
        return

    added, duplicates = await db.add_sorsa_keys(keys)
    await state.clear()
    await message.answer(
        f"✅ <b>Bulk Keys Added Successfully!</b>\n\n"
        f"• Added: <b>{added}</b> new keys\n"
        f"• Duplicates skipped: <b>{duplicates}</b>\n\n"
        f"Check pool status with /keys",
        parse_mode="HTML"
    )


@router.callback_query(F.data == "reset_keys")
async def cb_reset_keys(callback: types.CallbackQuery, db: Database):
    if not is_admin(callback.from_user.id):
        await callback.answer("Access restricted.", show_alert=True)
        return

    count = await db.reset_all_sorsa_keys()
    await callback.answer(f"Reactivated {count} keys!", show_alert=True)
    
    # Refresh dashboard
    stats = await db.get_sorsa_keys_stats()
    text = (
        "🔑 <b>Sorsa API Key Pool Management</b>\n\n"
        f"• 🟢 <b>Active Keys:</b> {stats['active']}\n"
        f"• 🟡 <b>Rate-Limited / Exhausted:</b> {stats['rate_limited']}\n"
        f"• 🔴 <b>Invalid Keys:</b> {stats['invalid']}\n"
        f"• 📁 <b>Total Keys in Pool:</b> {stats['total']}\n\n"
        "💡 <i>You can paste keys below or use:</i>\n"
        "• <code>/addkey &lt;key&gt;</code> - Add Sorsa API key\n"
        "• <code>/delinactive</code> - Delete all dead / rate-limited keys\n"
        "• <code>/resetkeys</code> - Reactivate all rate-limited keys\n"
        "• <code>/delkey &lt;key&gt;</code> - Remove a specific key"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_api_keys_keyboard())


@router.callback_query(F.data == "del_inactive_keys")
async def cb_del_inactive_keys(callback: types.CallbackQuery, db: Database):
    if not is_admin(callback.from_user.id):
        await callback.answer("Access restricted.", show_alert=True)
        return

    deleted = await db.delete_inactive_sorsa_keys()
    await callback.answer(f"🗑️ Deleted {deleted} inactive key(s)!", show_alert=True)

    # Refresh dashboard
    stats = await db.get_sorsa_keys_stats()
    text = (
        "🔑 <b>Sorsa API Key Pool Management</b>\n\n"
        f"• 🟢 <b>Active Keys:</b> {stats['active']}\n"
        f"• 🟡 <b>Rate-Limited / Exhausted:</b> {stats['rate_limited']}\n"
        f"• 🔴 <b>Invalid Keys:</b> {stats['invalid']}\n"
        f"• 📁 <b>Total Keys in Pool:</b> {stats['total']}\n\n"
        "💡 <i>You can paste keys below or use:</i>\n"
        "• <code>/addkey &lt;key&gt;</code> - Add Sorsa API key\n"
        "• <code>/delinactive</code> - Delete all dead / rate-limited keys\n"
        "• <code>/resetkeys</code> - Reactivate all rate-limited keys\n"
        "• <code>/delkey &lt;key&gt;</code> - Remove a specific key"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_api_keys_keyboard())


@router.callback_query(F.data == "list_keys")
async def cb_list_keys(callback: types.CallbackQuery, db: Database):
    if not is_admin(callback.from_user.id):
        await callback.answer("Access restricted.", show_alert=True)
        return

    all_keys = await db.get_all_sorsa_keys()
    if not all_keys:
        await callback.message.answer("ℹ️ No keys currently in the database pool.")
        await callback.answer()
        return

    lines = ["📋 <b>All Registered Sorsa API Keys:</b>\n"]
    for i, k in enumerate(all_keys, start=1):
        key_str = k["api_key"]
        masked = f"{key_str[:4]}...{key_str[-4:]}" if len(key_str) >= 10 else key_str
        status = k["status"]
        status_emoji = "🟢" if status == "active" else ("🟡" if status == "rate_limited" else "🔴")
        err = f" ({k['error_message']})" if k.get("error_message") else ""
        lines.append(f"{i}. {status_emoji} <code>{masked}</code> — {status}{err}")

    text = "\n".join(lines)
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()
