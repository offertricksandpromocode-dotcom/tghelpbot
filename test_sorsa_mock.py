import asyncio
import json
import unittest
from unittest.mock import MagicMock, AsyncMock
from bot.sorsa_client import SorsaClient


class TestSorsaClient(unittest.IsolatedAsyncioTestCase):
    async def test_comment_matching_primary_and_alt(self):
        client = SorsaClient(api_keys=["test_key"], base_url="http://mock-api.local")

        mock_response_data = {
            "comments": [
                {
                    "tweet_id": "111",
                    "text": "Random comment",
                    "author": {"username": "random_dude"}
                },
                {
                    "tweet_id": "112",
                    "text": "Great insights here!",
                    "author": {"username": "My_Alt_Account_99"}
                }
            ],
            "next_cursor": None
        }

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.text = AsyncMock(return_value=json.dumps(mock_response_data))

        mock_post_cm = MagicMock()
        mock_post_cm.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_post_cm.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_post_cm)
        mock_session.close = AsyncMock()
        mock_session.closed = False

        client._session = mock_session

        # 1. Test when user uses alt account (case-insensitive)
        result = await client.check_user_commented_on_tweet(
            tweet_link="https://x.com/someone/status/123",
            declared_handles=["main_user", "my_alt_account_99"]
        )
        self.assertTrue(result.found)
        self.assertEqual(result.matched_handle, "my_alt_account_99")
        self.assertIn("Great insights", result.comment_text)

        # 2. Test when user has NOT commented
        result_not_found = await client.check_user_commented_on_tweet(
            tweet_link="https://x.com/someone/status/123",
            declared_handles=["another_user", "unrelated_alt"]
        )
        self.assertFalse(result_not_found.found)
        self.assertIsNone(result_not_found.matched_handle)

        await client.close()

    async def test_key_rotation_on_rate_limit(self):
        """
        Verify that if key 1 fails with HTTP 429 Rate Limit,
        it rotates to key 2 which succeeds.
        """
        client = SorsaClient(api_keys=["key_exhausted_1", "key_working_2"])

        # Setup 2 responses: 1st is 429, 2nd is 200
        resp_429 = MagicMock()
        resp_429.status = 429
        resp_429.text = AsyncMock(return_value="Rate limit exceeded")

        resp_200 = MagicMock()
        resp_200.status = 200
        mock_data = {
            "comments": [
                {
                    "tweet_id": "222",
                    "text": "Verified comment!",
                    "author": {"username": "target_user"}
                }
            ]
        }
        resp_200.text = AsyncMock(return_value=json.dumps(mock_data))

        cm_429 = MagicMock()
        cm_429.__aenter__ = AsyncMock(return_value=resp_429)
        cm_429.__aexit__ = AsyncMock(return_value=None)

        cm_200 = MagicMock()
        cm_200.__aenter__ = AsyncMock(return_value=resp_200)
        cm_200.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        # Returns cm_429 on first call, cm_200 on second call
        mock_session.post = MagicMock(side_effect=[cm_429, cm_200])
        mock_session.close = AsyncMock()
        mock_session.closed = False

        client._session = mock_session

        result = await client.check_user_commented_on_tweet(
            tweet_link="https://x.com/someone/status/456",
            declared_handles=["target_user"]
        )

        self.assertTrue(result.found)
        self.assertEqual(result.matched_handle, "target_user")
        self.assertEqual(mock_session.post.call_count, 2)
        await client.close()

    async def test_deleted_tweet_stops_without_trying_other_keys(self):
        """
        Verify that if a tweet returns 404 Not Found (deleted / suspended),
        it does NOT retry multiple keys, but returns immediately.
        """
        client = SorsaClient(api_keys=["key_1", "key_2", "key_3"])

        resp_404 = MagicMock()
        resp_404.status = 404
        resp_404.text = AsyncMock(return_value="Tweet not found or deleted")

        cm_404 = MagicMock()
        cm_404.__aenter__ = AsyncMock(return_value=resp_404)
        cm_404.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=cm_404)
        mock_session.close = AsyncMock()
        mock_session.closed = False

        client._session = mock_session

        result = await client.check_user_commented_on_tweet(
            tweet_link="https://x.com/someone/status/789",
            declared_handles=["target_user"]
        )

        self.assertFalse(result.found)
        self.assertTrue(result.is_tweet_deleted)
        # Verify it was only called ONCE and did NOT try key_2 or key_3
        self.assertEqual(mock_session.post.call_count, 1)
        await client.close()


if __name__ == "__main__":
    unittest.main()
