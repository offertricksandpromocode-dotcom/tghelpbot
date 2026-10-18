from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot.database import Database
from bot.utils.twitter_helper import clean_handle
from bot.keyboards.inline import get_accounts_keyboard

router = Router(name="accounts_router")


class AccountStates(StatesGroup):
    waiting_for_primary = State()
    waiting_for_alt = State()


async def format_accounts_message(telegram_id: int, db: Database) -> tuple[str, list]:
    accounts = await db.get_user_x_accounts(telegram_id)
    if not accounts:
        text = (
            "⚙️ <b>Your Declared X (Twitter) Accounts</b>\n\n"
            "❌ <i>No accounts registered yet.</i>\n\n"
            "You must declare at least one X account before submitting links, "
            "so the bot can check your comments via Sorsa API."
        )
    else:
        lines = []
        for i, acc in enumerate(accounts, start=1):
            tag = "⭐ <b>Primary:</b>" if acc["is_primary"] else "🔹 <b>Alt:</b>"
            lines.append(f"{i}. {tag} @{acc['x_username']}")
        text = (
            "⚙️ <b>Your Declared X (Twitter) Accounts</b>\n\n"
            + "\n".join(lines)
            + "\n\n💡 <i>Comments made by your primary account or ANY of your declared alt accounts will be accepted!</i>"
        )
    return text, accounts


@router.message(Command("accounts", "myaccounts"))
async def cmd_accounts(message: types.Message, db: Database):
    text, accounts = await format_accounts_message(message.from_user.id, db)
    await message.answer(text, parse_mode="HTML", reply_markup=get_accounts_keyboard(accounts))


@router.callback_query(F.data == "manage_accounts")
async def cb_manage_accounts(callback: types.CallbackQuery, db: Database):
    text, accounts = await format_accounts_message(callback.from_user.id, db)
    await callback.message.answer(text, parse_mode="HTML", reply_markup=get_accounts_keyboard(accounts))
    await callback.answer()


@router.message(Command("addaccount", "setprimary"))
async def cmd_add_primary(message: types.Message, db: Database):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "⚠️ Please provide your X handle.\nExample: <code>/addaccount @elonmusk</code>",
            parse_mode="HTML"
        )
        return

    handle = clean_handle(args[1])
    if not handle:
        await message.answer("❌ Invalid X handle. Must contain only letters, numbers, and underscores (1-25 characters).")
        return

    added = await db.add_x_account(message.from_user.id, handle, is_primary=True)
    if added:
        await message.answer(f"✅ Primary X account registered: <b>@{handle}</b>", parse_mode="HTML")
    else:
        await message.answer(f"ℹ️ Account <b>@{handle}</b> is already registered to your profile.", parse_mode="HTML")


@router.message(Command("addalt"))
async def cmd_add_alt(message: types.Message, db: Database):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "⚠️ Please provide your alt X handle.\nExample: <code>/addalt @my_alt_account</code>",
            parse_mode="HTML"
        )
        return

    handle = clean_handle(args[1])
    if not handle:
        await message.answer("❌ Invalid X handle. Must contain only letters, numbers, and underscores.")
        return

    added = await db.add_x_account(message.from_user.id, handle, is_primary=False)
    if added:
        await message.answer(f"✅ Alt X account registered: <b>@{handle}</b>", parse_mode="HTML")
    else:
        await message.answer(f"ℹ️ Account <b>@{handle}</b> is already in your declared accounts.", parse_mode="HTML")


@router.message(Command("delalt", "delaccount"))
async def cmd_del_account(message: types.Message, db: Database):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("⚠️ Please specify the handle to remove.\nExample: <code>/delalt @handle</code>", parse_mode="HTML")
        return

    handle = clean_handle(args[1])
    if not handle:
        await message.answer("❌ Invalid handle.")
        return

    removed = await db.remove_x_account(message.from_user.id, handle)
    if removed:
        await message.answer(f"🗑️ Removed <b>@{handle}</b> from your declared accounts.", parse_mode="HTML")
    else:
        await message.answer(f"⚠️ <b>@{handle}</b> was not found in your declared accounts.", parse_mode="HTML")


# Interactive Callbacks for Adding / Removing
@router.callback_query(F.data == "prompt_add_primary")
async def cb_prompt_primary(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AccountStates.waiting_for_primary)
    await callback.message.answer(
        "✏️ Please send your <b>Primary X (Twitter) username</b> (e.g. <code>@yourhandle</code>):",
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "prompt_add_alt")
async def cb_prompt_alt(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AccountStates.waiting_for_alt)
    await callback.message.answer(
        "✏️ Please send your <b>Alt X (Twitter) username</b> (e.g. <code>@my_alt_handle</code>):",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AccountStates.waiting_for_primary)
async def state_receive_primary(message: types.Message, state: FSMContext, db: Database):
    handle = clean_handle(message.text)
    if not handle:
        await message.answer("❌ Invalid handle format. Please send a valid X username (e.g. <code>@handle</code>):", parse_mode="HTML")
        return

    await db.add_x_account(message.from_user.id, handle, is_primary=True)
    await state.clear()
    await message.answer(f"✅ Successfully set primary account to <b>@{handle}</b>!", parse_mode="HTML")


@router.message(AccountStates.waiting_for_alt)
async def state_receive_alt(message: types.Message, state: FSMContext, db: Database):
    handle = clean_handle(message.text)
    if not handle:
        await message.answer("❌ Invalid handle format. Please send a valid X username (e.g. <code>@alt_handle</code>):", parse_mode="HTML")
        return

    await db.add_x_account(message.from_user.id, handle, is_primary=False)
    await state.clear()
    await message.answer(f"✅ Successfully added alt account <b>@{handle}</b>!", parse_mode="HTML")


@router.callback_query(F.data.startswith("del_account:"))
async def cb_delete_account(callback: types.CallbackQuery, db: Database):
    handle = callback.data.split(":", 1)[1]
    await db.remove_x_account(callback.from_user.id, handle)
    await callback.answer(f"Removed @{handle}")
    
    text, accounts = await format_accounts_message(callback.from_user.id, db)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_accounts_keyboard(accounts))


@router.callback_query(F.data == "close_menu")
async def cb_close_menu(callback: types.CallbackQuery):
    await callback.message.delete()
    await callback.answer()
