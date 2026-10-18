from aiogram import Router, types
from aiogram.filters import CommandStart, Command
from bot.database import Database
from bot.config import config
from bot.keyboards.inline import get_no_accounts_keyboard

router = Router(name="start_router")


@router.message(CommandStart())
async def cmd_start(message: types.Message, db: Database):
    user = message.from_user
    if user:
        await db.upsert_user(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name
        )
    
    accounts = await db.get_user_x_accounts(user.id)
    stats = await db.get_user_stats(user.id)

    accounts_text = ""
    if accounts:
        accounts_list = ", ".join([f"@{acc['x_username']}" for acc in accounts])
        accounts_text = f"\n✅ <b>Your Declared X Accounts:</b> {accounts_list}"
    else:
        accounts_text = "\n⚠️ <b>No X accounts declared yet!</b> Please declare your handle before submitting links."

    welcome_text = (
        f"👋 <b>Welcome to the X (Twitter) Engagement Bot!</b>\n\n"
        f"Here is how this bot works:\n"
        f"1️⃣ <b>Declare your X Account(s):</b> Set your main handle and any alt accounts you plan to engage with.\n"
        f"2️⃣ <b>Submit an X Post:</b> Paste your tweet link here.\n"
        f"3️⃣ <b>Get 15 Assigned Posts:</b> The bot assigns you the 15 posts submitted above your link.\n"
        f"4️⃣ <b>Engage & Comment:</b> Leave a comment on each assigned post using any of your declared handles.\n"
        f"5️⃣ <b>Instant Verification:</b> Click <b>'🔍 Check Comments'</b> to verify your comments in real-time via the <b>Sorsa API</b>.\n\n"
        f"📊 <b>Your Activity:</b>\n"
        f"• Posts Submitted: <b>{stats['total_submitted']}</b>\n"
        f"• Posts Verified: <b>{stats['total_verified']}</b>\n"
        f"• Verified Comments Made: <b>{stats['total_comments_done']}</b>\n"
        f"{accounts_text}\n\n"
        f"Commands:\n"
        f"• /accounts - Manage your primary and alt accounts\n"
        f"• /addaccount &lt;@handle&gt; - Declare your primary X handle\n"
        f"• /addalt &lt;@handle&gt; - Add an alt X account\n"
        f"• /help - Bot instructions & FAQ"
    )

    if not accounts:
        await message.answer(welcome_text, parse_mode="HTML", reply_markup=get_no_accounts_keyboard())
    else:
        await message.answer(welcome_text, parse_mode="HTML")


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    help_text = (
        "📖 <b>Engagement Bot Help & Instructions</b>\n\n"
        "<b>Q: Can I use alternate (alt) accounts to comment?</b>\n"
        "A: Yes! You can declare as many alt accounts as you want using <code>/addalt @username</code>. "
        "When checking comments, Sorsa API verifies comments made by your primary or any of your declared alts.\n\n"
        "<b>Q: How are the 15 posts selected?</b>\n"
        "A: The bot takes the 15 most recent posts submitted prior to yours by other users in the queue.\n\n"
        "<b>Q: How does the verification work?</b>\n"
        "A: Click the <b>'🔍 Check Comments'</b> button under your task. The bot queries Sorsa API's comments "
        "endpoint directly for each assigned post to detect if your handle left a comment.\n\n"
        "<b>Commands:</b>\n"
        "• <code>/accounts</code> - View & manage your declared handles\n"
        "• <code>/addaccount @yourhandle</code> - Set your primary X handle\n"
        "• <code>/addalt @althandle</code> - Add an alt account\n"
        "• <code>/delalt @althandle</code> - Remove an alt account\n"
        "• <code>/stats</code> - View your statistics"
    )
    await message.answer(help_text, parse_mode="HTML")
