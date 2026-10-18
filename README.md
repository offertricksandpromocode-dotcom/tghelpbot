# Telegram X (Twitter) Engagement Bot with Sorsa API Verification

A Telegram bot built with **Python**, **aiogram 3.x**, **aiosqlite**, and the **Sorsa API** (`https://api.sorsa.io/v3`).

When a user submits an X (Twitter) post link, the bot automatically assigns them the **15 posts submitted above their link** in the queue. The bot provides an inline button to check if the user commented on each assigned post. Users can engage using alternate (alt) X accounts, as long as they declare them first. Verification is performed in real-time using a **multi-key pool with automated rotation and smart error handling via Sorsa API**.

---

## 🌟 Key Features

1. **Reciprocation Queue (15 Posts Above):**
   - When a user submits an X post URL, the bot queries the queue for the previous 15 posts submitted by other users.
   - Posts from the submitter themselves are excluded from assignments.
   - If the queue has fewer than 15 posts (e.g. at initial launch), it assigns all available previous posts.

2. **Primary & Alt X Account Declaration:**
   - Users can register a primary X account (e.g., `@main_crypto`).
   - Users can register multiple alternate (alt) X accounts (e.g., `@alt_degen`, `@trader_alt`).
   - Sorsa API comment check verifies if **any** of the user's declared accounts left a comment on the target tweet.

3. **Bulk Sorsa API Keys & Automated Rotation:**
   - Paste dozens of Sorsa API keys at once via `.env` or directly through the Telegram bot with `/addkeys`.
   - **Automatic Failover:** If an API key encounters an issue (`401 Unauthorized`, `403 Forbidden`, `429 Rate Limit`, or `402 Quota Exceeded`), the bot instantly rotates to the next active key in the pool without interrupting the verification flow!
   - View, reset, and manage the key pool via `/keys` or `/apikeys`.

4. **Smart Error Handling (No Redundant Retries for Deleted Tweets):**
   - If a tweet is deleted, private, or suspended (`404 Not Found` or tweet deleted message), the bot **immediately stops checking that tweet without wasting other API keys**.
   - The bot automatically waives deleted tweets (`🗑️ Waived (Tweet Deleted on X)`) so users aren't permanently blocked from finishing their task because of another user deleting a post!

5. **Async & Zero-Config SQLite Persistence:**
   - Powered by `aiosqlite` with foreign key constraints and transactional integrity.
   - Stores users, declared accounts, posts queue, key pool status, and individual task verification records.

---

## 📁 Project Structure

```text
├── bot/
│   ├── __init__.py
│   ├── config.py                 # Configuration loader (reads .env, bulk keys)
│   ├── database.py               # Async SQLite schema, queue & key pool operations
│   ├── sorsa_client.py           # Sorsa API client with multi-key rotation & smart error handling
│   ├── handlers/
│   │   ├── __init__.py           # Handler router aggregation
│   │   ├── start.py              # /start and /help commands
│   │   ├── accounts.py           # /accounts, /addaccount, /addalt, /delalt
│   │   ├── posts.py              # Link listener & 15-post assignment logic
│   │   ├── verification.py       # Inline callback verification, waiving & live updates
│   │   └── admin.py              # /keys, /addkeys, /resetkeys, /delkey, /stats
│   ├── keyboards/
│   │   ├── __init__.py
│   │   └── inline.py             # Dynamic inline keyboards (tasks, accounts, keys)
│   └── utils/
│       ├── __init__.py
│       └── twitter_helper.py     # Tweet URL parser and handle normalizer
├── .env.example                  # Environment variables template
├── requirements.txt              # Project dependencies
├── test_bot_logic.py             # Integration tests for DB, queue, & key pool
├── test_sorsa_mock.py            # Unit tests for multi-key rotation & deleted tweet exit
├── main.py                       # Bot entry point
└── README.md
```

---

## 🚀 Quick Setup & Installation

### 1. Prerequisites
- Python 3.10 or higher (Python 3.13 tested)

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure `.env`
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Edit `.env` and fill in your credentials:
```ini
# Telegram Bot Token from @BotFather
BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz

# Sorsa API Keys (paste bulk keys separated by commas, spaces, or newlines)
SORSA_API_KEYS=key_1, key_2, key_3, key_4

# Sorsa API Base URL
SORSA_API_BASE_URL=https://api.sorsa.io/v3

# Number of posts above to assign (default 15)
ASSIGNMENT_COUNT=15

# Database file location
DATABASE_PATH=engagement_bot.db

# Optional: Telegram user IDs for admin privileges (comma separated)
ADMIN_IDS=123456789
```

---

## 🤖 Running the Bot

Run the bot with:
```bash
python main.py
```

---

## 🧪 Running the Tests

Verify database operations, 15-post queue logic, multi-key rotation on 429, and early exit on 404:

```bash
python test_bot_logic.py
python test_sorsa_mock.py
```

---

## 🔑 Managing API Keys

You can easily manage the Sorsa API key pool at any time without restarting the bot:

| Command | Description |
| :--- | :--- |
| `/keys` or `/apikeys` | View status of key pool (Active, Rate-Limited, Invalid, Total) with quick-action buttons. |
| `/addkeys key1 key2 ...` | Paste one or dozens of keys separated by spaces, commas, or newlines. |
| `/resetkeys` | Reactivate all rate-limited or exhausted keys back to active status. |
| `/delkey <api_key>` | Remove a specific key from the pool. |
| Button `[➕ Add Bulk Keys]` | Interactive prompt to paste bulk keys directly in chat. |

---

## 📖 Bot Commands & User Workflow

### 1. Register X Handles
Before submitting a post, users declare the X handles they use to comment:
- `/addaccount @yourhandle` — Sets your primary X username.
- `/addalt @youralthandle` — Adds an alternate X username.
- `/accounts` — Opens the interactive accounts dashboard to view or delete accounts.

### 2. Submit an X Link
Paste any public X / Twitter post link:
- `https://x.com/username/status/1234567890123456789`
- `https://twitter.com/username/status/1234567890123456789`

### 3. Receive Assigned Posts
The bot responds with:
- Your submitted post link.
- Up to 15 assigned posts submitted prior to yours by other users.
- Verification status for each assigned post (`⏳ Pending` or `✅ Verified`).
- An inline button: **`[🔍 Check Comments (0/15)]`**.

### 4. Verify Comments with Sorsa API
1. Comment on each assigned post using any of your declared X accounts.
2. Click **`[🔍 Check Comments]`**.
3. The bot queries Sorsa API's comments endpoint (`POST /v3/comments`).
4. If an API key hits a rate limit or runs out of credits, it **automatically switches to another key**.
5. If an assigned tweet has been deleted or suspended on X, the bot **does not retry multiple keys** and automatically waives it so you can complete your queue!
6. Once all 15 assigned posts are verified or waived, your submission is approved in the pool.
