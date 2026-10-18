import logging
from aiogram import Router, types, F
from bot.database import Database
from bot.sorsa_client import SorsaClient
from bot.keyboards.inline import get_task_keyboard
from bot.handlers.posts import format_assignment_message

logger = logging.getLogger(__name__)
router = Router(name="verification_router")


@router.callback_query(F.data.startswith("check_task:"))
async def cb_check_task(
    callback: types.CallbackQuery,
    db: Database,
    sorsa: SorsaClient
):
    try:
        submitted_post_id = int(callback.data.split(":", 1)[1])
    except ValueError:
        await callback.answer("Invalid post ID.", show_alert=True)
        return

    telegram_id = callback.from_user.id

    # Retrieve post
    post = await db.get_post_by_id(submitted_post_id)
    if not post:
        await callback.answer("Post not found in database.", show_alert=True)
        return

    clicker_id = callback.from_user.id
    submitter_id = post["telegram_id"]

    # In groups, only the post author or an admin can trigger the check
    from bot.handlers.admin import is_admin
    if clicker_id != submitter_id and not is_admin(clicker_id):
        await callback.answer(
            "⚠️ Only the user who submitted this post (or an admin) can verify comments!",
            show_alert=True
        )
        return

    # Check declared accounts of the post author
    user_accounts = await db.get_user_x_accounts(submitter_id)
    if not user_accounts:
        await callback.answer(
            "⚠️ Author has not declared an X account yet! Use /accounts to set your handle.",
            show_alert=True
        )
        return

    declared_handles = [acc["x_username"] for acc in user_accounts]

    # Fetch current assignments
    assignments = await db.get_assignments(submitted_post_id)
    if not assignments:
        await callback.answer("No assignments associated with this post.", show_alert=True)
        return

    pending_assignments = [a for a in assignments if not a["is_verified"]]

    if not pending_assignments:
        await callback.answer("✅ All comments are already verified!", show_alert=True)
        return

    await callback.answer("🔍 Checking comments via Sorsa API, please wait a moment...")

    newly_verified = 0
    deleted_count = 0
    errors = []

    for item in pending_assignments:
        tweet_url = item["tweet_url"]
        result = await sorsa.check_user_commented_on_tweet(tweet_url, declared_handles)

        if result.is_tweet_deleted:
            # Tweet deleted or suspended on X: waive assignment so user is not blocked
            await db.mark_assignment_verified(item["assignment_id"], "waived_deleted_tweet")
            deleted_count += 1
        elif result.found and result.matched_handle:
            await db.mark_assignment_verified(item["assignment_id"], result.matched_handle)
            newly_verified += 1
        elif result.error_message:
            errors.append(result.error_message)

    # Fetch submitter's info to retain their TG username in the message header
    submitter_user = await db.get_user(submitter_id)
    submitter_mention = None
    if submitter_user:
        if submitter_user.get("username"):
            submitter_mention = f"@{submitter_user['username']}"
        elif submitter_user.get("first_name"):
            submitter_mention = f'<a href="tg://user?id={submitter_id}">{submitter_user["first_name"]}</a>'
        else:
            submitter_mention = f"User {submitter_id}"

    # Re-fetch updated assignments
    updated_assignments = await db.get_assignments(submitted_post_id)
    msg_text, verified_count, total_count, is_completed = format_assignment_message(
        post["tweet_url"],
        updated_assignments,
        declared_handles,
        submitter_mention=submitter_mention
    )

    if is_completed:
        await db.mark_submitted_post_completed(submitted_post_id)

    # Edit the message with updated status
    keyboard = get_task_keyboard(submitted_post_id, verified_count, total_count, is_completed)
    try:
        await callback.message.edit_text(
            msg_text,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=keyboard
        )
    except Exception as e:
        logger.debug("Message edit skipped (possibly no visual change): %s", e)

    # Send toast notification to user
    if is_completed:
        await callback.message.answer(
            f"🎉 <b>Success!</b> All {total_count}/{total_count} comments have been verified!\n"
            f"Your post is now fully active in the engagement queue.",
            parse_mode="HTML"
        )
    elif newly_verified > 0 or deleted_count > 0:
        details = []
        if newly_verified > 0:
            details.append(f"Verified <b>{newly_verified}</b> new comment(s)")
        if deleted_count > 0:
            details.append(f"Waived <b>{deleted_count}</b> deleted tweet(s)")
        await callback.message.answer(
            f"✅ {' & '.join(details)}! Progress: <b>{verified_count}/{total_count}</b>",
            parse_mode="HTML"
        )
    else:
        err_hint = f"\n⚠️ <i>{errors[0]}</i>" if errors else ""
        await callback.message.answer(
            f"ℹ️ No new comments detected yet ({verified_count}/{total_count} verified).\n"
            f"Make sure you left comments using one of your declared accounts: "
            f"<b>{', '.join(['@' + h for h in declared_handles])}</b>.{err_hint}",
            parse_mode="HTML"
        )


@router.callback_query(F.data.startswith("refresh_task:"))
async def cb_refresh_task(callback: types.CallbackQuery, db: Database):
    try:
        submitted_post_id = int(callback.data.split(":", 1)[1])
    except ValueError:
        await callback.answer("Invalid post ID.")
        return

    post = await db.get_post_by_id(submitted_post_id)
    if not post:
        await callback.answer("Post not found.")
        return

    submitter_id = post["telegram_id"]
    user_accounts = await db.get_user_x_accounts(submitter_id)
    declared_handles = [acc["x_username"] for acc in user_accounts]
    assignments = await db.get_assignments(submitted_post_id)

    msg_text, verified_count, total_count, is_completed = format_assignment_message(
        post["tweet_url"],
        assignments,
        declared_handles
    )
    keyboard = get_task_keyboard(submitted_post_id, verified_count, total_count, is_completed)

    try:
        await callback.message.edit_text(
            msg_text,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=keyboard
        )
        await callback.answer("Refreshed!")
    except Exception:
        await callback.answer("Already up to date.")


@router.callback_query(F.data.startswith("task_done:"))
async def cb_task_done(callback: types.CallbackQuery):
    await callback.answer("🎉 This task is already 100% completed!", show_alert=True)
