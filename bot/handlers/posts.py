import logging
from typing import Optional
from aiogram import Router, types, F
from bot.database import Database
from bot.config import config
from bot.utils.twitter_helper import extract_tweet_info
from bot.keyboards.inline import get_task_keyboard, get_no_accounts_keyboard

logger = logging.getLogger(__name__)
router = Router(name="posts_router")


def format_assignment_message(
    submitted_url: str,
    assignments: list,
    declared_handles: list[str],
    auto_activated_handle: Optional[str] = None,
    submitter_mention: Optional[str] = None
) -> tuple[str, int, int, bool]:
    total_count = len(assignments)
    verified_count = sum(1 for a in assignments if a["is_verified"])
    is_completed = total_count > 0 and verified_count == total_count

    handles_str = ", ".join([f"@{h}" for h in declared_handles]) if declared_handles else "None"

    lines = [
        "📌 <b>New X Post Submitted!</b>\n",
    ]

    if submitter_mention:
        lines.append(f"👤 <b>Submitted by:</b> {submitter_mention}\n")

    lines.append(f"🔗 <b>Post Link:</b> {submitted_url}\n")

    if auto_activated_handle:
        lines.append(
            f"✨ <b>Auto-Activated Account:</b> @{auto_activated_handle}\n"
            f"<i>(Detected from your link. Use /addalt to add more accounts if needed)</i>\n"
        )

    lines.extend([
        f"🎯 <b>Your Declared Handles:</b> {handles_str}\n",
        f"📋 <b>Your Assigned Posts to Comment ({verified_count}/{total_count}):</b>"
    ])

    if total_count == 0:
        lines.append(
            "\n<i>No previous posts are in the queue yet! You are the first submitter. "
            "Your link is registered in the pool for future users.</i>"
        )
    else:
        for idx, item in enumerate(assignments, start=1):
            url = item["tweet_url"]
            author = item.get("author_handle")
            author_str = f"@{author}" if author and author.lower() not in ("i", "status") else "X Post"

            if item["is_verified"]:
                if item.get("verified_by_handle") == "waived_deleted_tweet":
                    status_str = "🗑️ <i>Waived (Tweet Deleted on X)</i>"
                else:
                    by = f" by @{item['verified_by_handle']}" if item.get("verified_by_handle") else ""
                    status_str = f"✅ <b>Verified</b>{by}"
            else:
                status_str = "⏳ <i>Pending</i>"

            lines.append(f"{idx}. 👤 <b>{author_str}</b>: <a href=\"{url}\">{url}</a>\n   └ Status: {status_str}")

        lines.append(
            "\n💡 <i>Leave a comment on the posts above using any of your declared X accounts. "
            "Once posted, click the button below to verify your comments with Sorsa API!</i>"
        )

    if is_completed:
        lines.append("\n🎉 <b>All assigned comments have been successfully verified!</b>")

    text = "\n".join(lines)
    return text, verified_count, total_count, is_completed


@router.message(F.text)
async def handle_potential_link(message: types.Message, db: Database):
    text = message.text.strip()
    if text.startswith("/"):
        return  # Let command handlers take care of commands

    tweet_info = extract_tweet_info(text)
    if not tweet_info:
        # Not a tweet link
        return

    canonical_url, tweet_id, username = tweet_info
    telegram_id = message.from_user.id
    is_group = message.chat.type in ("group", "supergroup")
    chat_id = message.chat.id if is_group else None
    user_mention = message.from_user.mention_html()

    # Automatically delete the user's raw pasted link to keep chat/group clean
    try:
        await message.delete()
    except Exception as e:
        logger.debug("Could not delete user link message: %s", e)

    # Ensure user exists in users table
    user = message.from_user
    if user:
        await db.upsert_user(
            telegram_id=telegram_id,
            username=user.username,
            first_name=user.first_name
        )

    # Check if user has declared accounts
    user_accounts = await db.get_user_x_accounts(telegram_id)
    auto_activated_handle = None

    if not user_accounts:
        # Auto-activate user's account from the tweet link!
        clean_user = username.strip().lower() if username else ""
        if clean_user and clean_user not in ("i", "status", "web"):
            await db.add_x_account(telegram_id, clean_user, is_primary=True)
            user_accounts = await db.get_user_x_accounts(telegram_id)
            auto_activated_handle = clean_user
        else:
            # Fallback if handle couldn't be extracted from a redirect link
            await message.answer(
                f"⚠️ {user_mention}, <b>Action Required: Declare your X Account</b>\n\n"
                "Before submitting posts, you must register the X (Twitter) account you use to comment.\n"
                "Please click below to register:",
                parse_mode="HTML",
                reply_markup=get_no_accounts_keyboard()
            )
            return

    declared_handles = [acc["x_username"] for acc in user_accounts]

    # Check if this tweet was already submitted
    existing_post = await db.get_post_by_tweet_id(tweet_id)
    if existing_post:
        # Already submitted - retrieve assignments
        assignments = await db.get_assignments(existing_post["id"])
        msg_text, verified_count, total_count, is_completed = format_assignment_message(
            existing_post["tweet_url"],
            assignments,
            declared_handles,
            submitter_mention=user_mention
        )
        await message.answer(
            "ℹ️ <b>This tweet has already been registered!</b>\n\n" + msg_text,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=get_task_keyboard(
                existing_post["id"],
                verified_count,
                total_count,
                is_completed
            )
        )
        return

    # Add post to queue
    new_post_id = await db.add_post(
        telegram_id=telegram_id,
        tweet_id=tweet_id,
        tweet_url=canonical_url,
        author_handle=username,
        chat_id=chat_id
    )
    if not new_post_id:
        await message.answer("❌ Error registering post in database. Please try again.")
        return

    # Fetch 15 posts submitted above this one (scoped to group if in group)
    posts_above = await db.get_posts_above(
        current_post_id=new_post_id,
        exclude_telegram_id=telegram_id,
        limit=config.ASSIGNMENT_COUNT,
        chat_id=chat_id
    )

    assigned_post_ids = [p["id"] for p in posts_above]
    await db.create_assignments(telegram_id, new_post_id, assigned_post_ids)

    # Get created assignments
    assignments = await db.get_assignments(new_post_id)

    msg_text, verified_count, total_count, is_completed = format_assignment_message(
        canonical_url,
        assignments,
        declared_handles,
        auto_activated_handle=auto_activated_handle,
        submitter_mention=user_mention
    )

    await message.answer(
        msg_text,
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=get_task_keyboard(
            new_post_id,
            verified_count,
            total_count,
            is_completed
        )
    )
