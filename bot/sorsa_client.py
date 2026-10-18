import aiohttp
import logging
from typing import List, Set, Optional, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from bot.database import Database

logger = logging.getLogger(__name__)


class VerificationResult:
    def __init__(
        self,
        found: bool = False,
        matched_handle: Optional[str] = None,
        comment_text: Optional[str] = None,
        error_message: Optional[str] = None,
        is_tweet_deleted: bool = False,
    ):
        self.found = found
        self.matched_handle = matched_handle
        self.comment_text = comment_text
        self.error_message = error_message
        self.is_tweet_deleted = is_tweet_deleted

    def __repr__(self):
        return (
            f"<VerificationResult found={self.found} handle={self.matched_handle} "
            f"deleted={self.is_tweet_deleted} error={self.error_message}>"
        )


def is_tweet_deleted_or_unavailable(status: int, body_text: str) -> bool:
    """Detects if error indicates the tweet itself is deleted, private, or suspended."""
    if status == 404:
        return True
    lower = body_text.lower()
    indicators = [
        "not found", "deleted", "suspended", "does not exist",
        "unavailable", "blocked", "tweet not found", "no status found",
        "user has been suspended", "page does not exist"
    ]
    return any(ind in lower for ind in indicators)


def is_key_exhausted_or_invalid(status: int, body_text: str) -> bool:
    """Detects if error indicates the Sorsa API key is invalid, rate-limited, or out of quota."""
    if status in (401, 402, 403, 429):
        return True
    lower = body_text.lower()
    indicators = [
        "api key", "unauthorized", "quota", "credit", "rate limit",
        "forbidden", "exceeded", "payment required", "invalid token"
    ]
    return any(ind in lower for ind in indicators)


class SorsaClient:
    def __init__(
        self,
        api_keys: Optional[List[str]] = None,
        base_url: str = "https://api.sorsa.io/v3",
        db: Optional["Database"] = None,
    ):
        self.in_memory_keys: List[str] = [k.strip() for k in (api_keys or []) if k.strip()]
        self.base_url = base_url.rstrip("/")
        self.db = db
        self._session: Optional[aiohttp.ClientSession] = None

    async def get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=20)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def get_available_keys(self) -> List[str]:
        """Fetches active keys from database or in-memory fallback."""
        if self.db:
            db_keys = await self.db.get_active_sorsa_keys()
            if db_keys:
                return db_keys
        return list(self.in_memory_keys)

    def _extract_username(self, comment: Dict[str, Any]) -> Optional[str]:
        """Safely extracts username from various possible Sorsa/X JSON schema representations."""
        # 1. Standard author object
        author = comment.get("author")
        if isinstance(author, dict):
            username = author.get("username") or author.get("screen_name")
            if username:
                return str(username).lower().lstrip("@")

        # 2. User object
        user = comment.get("user")
        if isinstance(user, dict):
            username = user.get("username") or user.get("screen_name")
            if username:
                return str(username).lower().lstrip("@")

        # 3. Direct field
        direct = comment.get("author_username") or comment.get("username")
        if direct:
            return str(direct).lower().lstrip("@")

        return None

    def _extract_text(self, comment: Dict[str, Any]) -> str:
        return comment.get("text") or comment.get("full_text") or ""

    async def check_user_commented_on_tweet(
        self,
        tweet_link: str,
        declared_handles: List[str],
        max_pages: int = 3
    ) -> VerificationResult:
        """
        Checks if any of the declared handles have commented on the given tweet URL.
        Features:
        - Automatically rotates to the next API key if current key fails (401/403/429/quota).
        - Stops immediately without retrying other keys if the tweet is deleted or unavailable.
        """
        target_handles: Set[str] = {
            h.lower().strip().lstrip("@") for h in declared_handles if h.strip()
        }
        if not target_handles:
            return VerificationResult(
                found=False,
                error_message="No X account handles declared for user."
            )

        keys_to_try = await self.get_available_keys()
        if not keys_to_try:
            return VerificationResult(
                found=False,
                error_message="No active Sorsa API keys available. Please add keys via /addkeys or check .env"
            )

        session = await self.get_session()
        url = f"{self.base_url}/comments"

        last_error = ""

        # Try active keys in rotation
        for current_key in keys_to_try:
            headers = {
                "ApiKey": current_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            }

            key_failed = False
            next_cursor = None
            found_comment = False
            matched_result = None

            for page in range(max_pages):
                payload = {
                    "tweet_link": tweet_link,
                    "order_by": "Recency"
                }
                if next_cursor:
                    payload["next_cursor"] = next_cursor

                try:
                    async with session.post(url, headers=headers, json=payload) as resp:
                        body_text = await resp.text()

                        # 1. Check if the tweet itself is deleted or suspended
                        # IMPORTANT: Do NOT retry other keys if the tweet itself is deleted!
                        if is_tweet_deleted_or_unavailable(resp.status, body_text):
                            logger.warning(
                                "Tweet %s is deleted or unavailable (status %d). Not retrying other keys.",
                                tweet_link, resp.status
                            )
                            return VerificationResult(
                                found=False,
                                is_tweet_deleted=True,
                                error_message="Tweet is deleted or unavailable."
                            )

                        # 2. Check if this API key is exhausted, invalid, or rate-limited
                        if is_key_exhausted_or_invalid(resp.status, body_text):
                            key_status = "invalid" if resp.status in (401, 403) else "rate_limited"
                            logger.warning(
                                "Sorsa API key (...%s) failed with status %d: %s. Rotating to next key...",
                                current_key[-6:] if len(current_key) >= 6 else current_key,
                                resp.status,
                                body_text[:100]
                            )
                            if self.db:
                                await self.db.mark_sorsa_key_failed(
                                    current_key, key_status, f"HTTP {resp.status}: {body_text[:120]}"
                                )
                            if current_key in self.in_memory_keys:
                                self.in_memory_keys.remove(current_key)
                            
                            key_failed = True
                            last_error = f"API Key error ({resp.status})"
                            break  # Break inner pagination loop and rotate to next key

                        # 3. Other unexpected status
                        if resp.status != 200:
                            logger.error("Sorsa API returned status %d: %s", resp.status, body_text)
                            last_error = f"Sorsa API returned status {resp.status}"
                            key_failed = True
                            break

                        # Successful response
                        if self.db:
                            await self.db.mark_sorsa_key_used(current_key)

                        import json
                        try:
                            data = json.loads(body_text)
                        except Exception:
                            data = {}

                except aiohttp.ClientConnectorError as e:
                    logger.error("Network connection error to Sorsa API: %s", e)
                    last_error = "Network connection error"
                    key_failed = True
                    break
                except Exception as e:
                    logger.exception("Unexpected error querying Sorsa API: %s", e)
                    last_error = f"Unexpected error: {str(e)}"
                    key_failed = True
                    break

                comments = (
                    data.get("comments")
                    or data.get("tweets")
                    or data.get("data")
                    or []
                )

                for comment in comments:
                    if not isinstance(comment, dict):
                        continue
                    author_username = self._extract_username(comment)
                    if author_username and author_username in target_handles:
                        text = self._extract_text(comment)
                        found_comment = True
                        matched_result = VerificationResult(
                            found=True,
                            matched_handle=author_username,
                            comment_text=text
                        )
                        break

                if found_comment:
                    return matched_result

                # Check pagination
                next_cursor = data.get("next_cursor")
                if not next_cursor or not comments:
                    break

            if not key_failed:
                # The key worked properly and returned the comment thread (user just hasn't commented yet)
                return VerificationResult(found=False)

        # All keys in the pool were exhausted or failed
        return VerificationResult(
            found=False,
            error_message=f"All Sorsa API keys failed or exhausted. Last error: {last_error}"
        )
