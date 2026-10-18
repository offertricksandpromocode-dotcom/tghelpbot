import aiosqlite
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def init_db(self):
        """Initializes tables and indexes."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA foreign_keys = ON;")
            
            # Users table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Declared X accounts (primary + alts)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_x_accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER NOT NULL,
                    x_username TEXT NOT NULL,
                    is_primary INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(telegram_id, x_username),
                    FOREIGN KEY (telegram_id) REFERENCES users (telegram_id) ON DELETE CASCADE
                );
            """)

            # Submitted posts queue
            await db.execute("""
                CREATE TABLE IF NOT EXISTS posts_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER NOT NULL,
                    chat_id INTEGER,
                    tweet_id TEXT NOT NULL UNIQUE,
                    tweet_url TEXT NOT NULL,
                    author_handle TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'pending',
                    FOREIGN KEY (telegram_id) REFERENCES users (telegram_id) ON DELETE CASCADE
                );
            """)

            # Safe migration for existing DB
            try:
                await db.execute("ALTER TABLE posts_queue ADD COLUMN chat_id INTEGER;")
                await db.commit()
            except Exception:
                pass

            # Task assignments: posts assigned to a user for their submission
            await db.execute("""
                CREATE TABLE IF NOT EXISTS task_assignments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER NOT NULL,
                    submitted_post_id INTEGER NOT NULL,
                    assigned_post_id INTEGER NOT NULL,
                    is_verified INTEGER DEFAULT 0,
                    verified_by_handle TEXT,
                    verified_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (telegram_id) REFERENCES users (telegram_id) ON DELETE CASCADE,
                    FOREIGN KEY (submitted_post_id) REFERENCES posts_queue (id) ON DELETE CASCADE,
                    FOREIGN KEY (assigned_post_id) REFERENCES posts_queue (id) ON DELETE CASCADE
                );
            """)

            # Sorsa API Keys pool table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS sorsa_api_keys (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    api_key TEXT NOT NULL UNIQUE,
                    status TEXT DEFAULT 'active',
                    error_message TEXT,
                    fail_count INTEGER DEFAULT 0,
                    last_used_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            await db.commit()
            logger.info("Database initialized successfully at %s", self.db_path)

    # User Management
    async def upsert_user(self, telegram_id: int, username: Optional[str], first_name: Optional[str]):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO users (telegram_id, username, first_name)
                VALUES (?, ?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET
                    username = excluded.username,
                    first_name = excluded.first_name;
            """, (telegram_id, username, first_name))
            await db.commit()

    # X Accounts Management
    async def add_x_account(self, telegram_id: int, x_username: str, is_primary: bool = False) -> bool:
        """Adds an X handle for the user. Returns True if added, False if already exists."""
        x_username = x_username.lower().strip().lstrip("@")
        async with aiosqlite.connect(self.db_path) as db:
            # Check if user has any accounts yet. If not, make this one primary
            async with db.execute(
                "SELECT COUNT(*) FROM user_x_accounts WHERE telegram_id = ?",
                (telegram_id,)
            ) as cursor:
                count = (await cursor.fetchone())[0]
                if count == 0:
                    is_primary = True

            try:
                await db.execute("""
                    INSERT INTO user_x_accounts (telegram_id, x_username, is_primary)
                    VALUES (?, ?, ?)
                """, (telegram_id, x_username, 1 if is_primary else 0))
                await db.commit()
                return True
            except aiosqlite.IntegrityError:
                return False

    async def get_user_x_accounts(self, telegram_id: int) -> List[Dict[str, Any]]:
        """Returns list of declared X accounts for the user."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT id, x_username, is_primary, created_at
                FROM user_x_accounts
                WHERE telegram_id = ?
                ORDER BY is_primary DESC, id ASC
            """, (telegram_id,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def remove_x_account(self, telegram_id: int, x_username: str) -> bool:
        """Removes a declared X account. Returns True if removed."""
        x_username = x_username.lower().strip().lstrip("@")
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                DELETE FROM user_x_accounts
                WHERE telegram_id = ? AND x_username = ?
            """, (telegram_id, x_username))
            await db.commit()
            return cursor.rowcount > 0

    # Posts Queue Management
    async def add_post(
        self,
        telegram_id: int,
        tweet_id: str,
        tweet_url: str,
        author_handle: Optional[str] = None,
        chat_id: Optional[int] = None
    ) -> Optional[int]:
        """
        Adds a tweet to the posts queue with optional group chat_id.
        Returns the new post ID, or None if tweet already exists.
        """
        async with aiosqlite.connect(self.db_path) as db:
            try:
                cursor = await db.execute("""
                    INSERT INTO posts_queue (telegram_id, chat_id, tweet_id, tweet_url, author_handle)
                    VALUES (?, ?, ?, ?, ?)
                """, (telegram_id, chat_id, tweet_id, tweet_url, author_handle))
                await db.commit()
                return cursor.lastrowid
            except aiosqlite.IntegrityError:
                return None

    async def get_post_by_tweet_id(self, tweet_id: str) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT id, telegram_id, chat_id, tweet_id, tweet_url, author_handle, created_at, status
                FROM posts_queue
                WHERE tweet_id = ?
            """, (tweet_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def get_post_by_id(self, post_id: int) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT id, telegram_id, chat_id, tweet_id, tweet_url, author_handle, created_at, status
                FROM posts_queue
                WHERE id = ?
            """, (post_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def get_posts_above(
        self,
        current_post_id: int,
        exclude_telegram_id: int,
        limit: int = 15,
        chat_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetches up to `limit` posts submitted prior to `current_post_id`,
        excluding posts submitted by the same user.
        If chat_id is provided, filters by group chat_id.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if chat_id is not None:
                query = """
                    SELECT id, telegram_id, chat_id, tweet_id, tweet_url, author_handle, created_at, status
                    FROM posts_queue
                    WHERE id < ? AND telegram_id != ? AND chat_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                """
                params = (current_post_id, exclude_telegram_id, chat_id, limit)
            else:
                query = """
                    SELECT id, telegram_id, chat_id, tweet_id, tweet_url, author_handle, created_at, status
                    FROM posts_queue
                    WHERE id < ? AND telegram_id != ?
                    ORDER BY id DESC
                    LIMIT ?
                """
                params = (current_post_id, exclude_telegram_id, limit)

            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    # Task Assignments
    async def create_assignments(
        self,
        telegram_id: int,
        submitted_post_id: int,
        assigned_post_ids: List[int]
    ):
        """Creates assignment entries for a user's submitted post."""
        if not assigned_post_ids:
            return
        async with aiosqlite.connect(self.db_path) as db:
            records = [
                (telegram_id, submitted_post_id, assigned_id)
                for assigned_id in assigned_post_ids
            ]
            await db.executemany("""
                INSERT INTO task_assignments (telegram_id, submitted_post_id, assigned_post_id)
                VALUES (?, ?, ?)
            """, records)
            await db.commit()

    async def get_assignments(self, submitted_post_id: int) -> List[Dict[str, Any]]:
        """
        Retrieves all assigned posts and their verification status for a submitted post.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT 
                    ta.id AS assignment_id,
                    ta.submitted_post_id,
                    ta.assigned_post_id,
                    ta.is_verified,
                    ta.verified_by_handle,
                    ta.verified_at,
                    pq.tweet_id,
                    pq.tweet_url,
                    pq.author_handle
                FROM task_assignments ta
                JOIN posts_queue pq ON ta.assigned_post_id = pq.id
                WHERE ta.submitted_post_id = ?
                ORDER BY ta.id ASC
            """, (submitted_post_id,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def mark_assignment_verified(
        self,
        assignment_id: int,
        verified_by_handle: str
    ):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE task_assignments
                SET is_verified = 1,
                    verified_by_handle = ?,
                    verified_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (verified_by_handle, assignment_id))
            await db.commit()

    async def mark_submitted_post_completed(self, post_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE posts_queue
                SET status = 'verified'
                WHERE id = ?
            """, (post_id,))
            await db.commit()

    async def get_user_stats(self, telegram_id: int) -> Dict[str, int]:
        """Gets user stats: total submitted, verified, comments completed."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM posts_queue WHERE telegram_id = ?",
                (telegram_id,)
            ) as cursor:
                total_submitted = (await cursor.fetchone())[0]

            async with db.execute(
                "SELECT COUNT(*) FROM posts_queue WHERE telegram_id = ? AND status = 'verified'",
                (telegram_id,)
            ) as cursor:
                total_verified = (await cursor.fetchone())[0]

            async with db.execute(
                "SELECT COUNT(*) FROM task_assignments WHERE telegram_id = ? AND is_verified = 1",
                (telegram_id,)
            ) as cursor:
                total_comments_done = (await cursor.fetchone())[0]

            return {
                "total_submitted": total_submitted,
                "total_verified": total_verified,
                "total_comments_done": total_comments_done,
            }

    async def get_queue_stats(self) -> Dict[str, int]:
        """Gets global queue statistics."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM users") as cursor:
                total_users = (await cursor.fetchone())[0]
            async with db.execute("SELECT COUNT(*) FROM posts_queue") as cursor:
                total_posts = (await cursor.fetchone())[0]
            async with db.execute("SELECT COUNT(*) FROM task_assignments WHERE is_verified = 1") as cursor:
                verified_engagements = (await cursor.fetchone())[0]
            return {
                "total_users": total_users,
                "total_posts": total_posts,
                "verified_engagements": verified_engagements,
            }

    # Sorsa API Keys Management
    async def add_sorsa_keys(self, keys: List[str]) -> tuple[int, int]:
        """
        Adds multiple Sorsa API keys to the pool.
        Returns (added_count, duplicate_count).
        """
        added = 0
        duplicates = 0
        async with aiosqlite.connect(self.db_path) as db:
            for k in keys:
                cleaned = k.strip()
                if not cleaned:
                    continue
                try:
                    await db.execute("""
                        INSERT INTO sorsa_api_keys (api_key, status)
                        VALUES (?, 'active')
                    """, (cleaned,))
                    added += 1
                except aiosqlite.IntegrityError:
                    duplicates += 1
            await db.commit()
        return added, duplicates

    async def get_active_sorsa_keys(self) -> List[str]:
        """Returns list of active Sorsa API keys ordered by least recently used."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT api_key FROM sorsa_api_keys
                WHERE status = 'active'
                ORDER BY last_used_at ASC NULLS FIRST, id ASC
            """) as cursor:
                rows = await cursor.fetchall()
                return [r[0] for r in rows]

    async def get_all_sorsa_keys(self) -> List[Dict[str, Any]]:
        """Returns all keys and their status."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT id, api_key, status, error_message, fail_count, last_used_at, created_at
                FROM sorsa_api_keys
                ORDER BY id ASC
            """) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    async def mark_sorsa_key_used(self, api_key: str):
        """Updates last_used_at for an API key."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE sorsa_api_keys
                SET last_used_at = CURRENT_TIMESTAMP
                WHERE api_key = ?
            """, (api_key,))
            await db.commit()

    async def mark_sorsa_key_failed(self, api_key: str, status: str, error_message: str):
        """
        Marks a key as rate_limited or invalid and records error.
        status should be 'rate_limited' or 'invalid'.
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE sorsa_api_keys
                SET status = ?,
                    error_message = ?,
                    fail_count = fail_count + 1,
                    last_used_at = CURRENT_TIMESTAMP
                WHERE api_key = ?
            """, (status, error_message, api_key))
            await db.commit()

    async def reset_all_sorsa_keys(self) -> int:
        """Resets all non-active keys back to 'active'."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                UPDATE sorsa_api_keys
                SET status = 'active', error_message = NULL
                WHERE status != 'active'
            """)
            await db.commit()
            return cursor.rowcount

    async def remove_sorsa_key(self, api_key: str) -> bool:
        """Deletes a key from the pool."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                DELETE FROM sorsa_api_keys
                WHERE api_key = ?
            """, (api_key.strip(),))
            await db.commit()
            return cursor.rowcount > 0

    async def get_sorsa_keys_stats(self) -> Dict[str, int]:
        """Returns count of active, rate_limited, and invalid keys."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM sorsa_api_keys") as cursor:
                total = (await cursor.fetchone())[0]
            async with db.execute("SELECT COUNT(*) FROM sorsa_api_keys WHERE status = 'active'") as cursor:
                active = (await cursor.fetchone())[0]
            async with db.execute("SELECT COUNT(*) FROM sorsa_api_keys WHERE status = 'rate_limited'") as cursor:
                rate_limited = (await cursor.fetchone())[0]
            async with db.execute("SELECT COUNT(*) FROM sorsa_api_keys WHERE status = 'invalid'") as cursor:
                invalid = (await cursor.fetchone())[0]

            return {
                "total": total,
                "active": active,
                "rate_limited": rate_limited,
                "invalid": invalid,
            }
