from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Dict, Any


def get_task_keyboard(
    submitted_post_id: int,
    verified_count: int,
    total_count: int,
    is_completed: bool = False
) -> InlineKeyboardMarkup:
    """Keyboard attached to the assigned posts list message."""
    buttons = []
    
    if is_completed:
        verify_text = f"✅ All Comments Verified ({verified_count}/{total_count})"
        buttons.append([
            InlineKeyboardButton(text=verify_text, callback_data=f"task_done:{submitted_post_id}")
        ])
    else:
        verify_text = f"🔍 Check Comments ({verified_count}/{total_count})"
        buttons.append([
            InlineKeyboardButton(text=verify_text, callback_data=f"check_task:{submitted_post_id}")
        ])
        buttons.append([
            InlineKeyboardButton(text="🔄 Refresh List", callback_data=f"refresh_task:{submitted_post_id}"),
            InlineKeyboardButton(text="⚙️ My Accounts", callback_data="manage_accounts")
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_accounts_keyboard(accounts: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    """Keyboard for viewing and managing declared accounts."""
    buttons = []

    # Row for adding accounts
    buttons.append([
        InlineKeyboardButton(text="➕ Add / Update Primary", callback_data="prompt_add_primary"),
        InlineKeyboardButton(text="➕ Add Alt Account", callback_data="prompt_add_alt"),
    ])

    # If user has accounts, provide delete buttons for each
    for acc in accounts:
        handle = acc["x_username"]
        role = "Primary" if acc["is_primary"] else "Alt"
        buttons.append([
            InlineKeyboardButton(
                text=f"🗑️ Delete @{handle} ({role})",
                callback_data=f"del_account:{handle}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(text="🔙 Close Menu", callback_data="close_menu")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_no_accounts_keyboard() -> InlineKeyboardMarkup:
    """Keyboard prompting user to add their X account first."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="➕ Add Primary Account", callback_data="prompt_add_primary"),
                InlineKeyboardButton(text="➕ Add Alt Account", callback_data="prompt_add_alt"),
            ]
        ]
    )


def get_api_keys_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for Admin Sorsa API Keys Management."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="➕ Add Sorsa API Key(s)", callback_data="prompt_add_keys"),
            ],
            [
                InlineKeyboardButton(text="🗑️ Delete Inactive Keys", callback_data="del_inactive_keys"),
                InlineKeyboardButton(text="🔄 Reset to Active", callback_data="reset_keys"),
            ],
            [
                InlineKeyboardButton(text="📋 List All Keys", callback_data="list_keys"),
                InlineKeyboardButton(text="🔙 Close Menu", callback_data="close_menu"),
            ]
        ]
    )

