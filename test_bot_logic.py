import asyncio
import os
import unittest
from bot.database import Database
from bot.utils.twitter_helper import extract_tweet_info, clean_handle
from bot.sorsa_client import SorsaClient, VerificationResult


class TestEngagementBot(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.test_db_path = "test_engagement.db"
        if os.path.exists(self.test_db_path):
            os.remove(self.test_db_path)
        self.db = Database(self.test_db_path)
        await self.db.init_db()

    async def asyncTearDown(self):
        if os.path.exists(self.test_db_path):
            try:
                os.remove(self.test_db_path)
            except PermissionError:
                pass

    def test_twitter_helper(self):
        # Test clean_handle
        self.assertEqual(clean_handle("@ElonMusk"), "elonmusk")
        self.assertEqual(clean_handle("my_alt_account"), "my_alt_account")
        self.assertIsNone(clean_handle("invalid@handle!"))

        # Test extract_tweet_info
        url1 = "https://x.com/jack/status/20"
        res1 = extract_tweet_info(url1)
        self.assertIsNotNone(res1)
        canonical, tweet_id, username = res1
        self.assertEqual(canonical, "https://x.com/jack/status/20")
        self.assertEqual(tweet_id, "20")
        self.assertEqual(username, "jack")

        url2 = "https://twitter.com/elonmusk/status/1789123456789012345?s=20"
        res2 = extract_tweet_info(url2)
        self.assertIsNotNone(res2)
        self.assertEqual(res2[1], "1789123456789012345")
        self.assertEqual(res2[2], "elonmusk")

    async def test_accounts_and_alts(self):
        user_id = 111222333
        await self.db.upsert_user(user_id, "testuser", "Test")

        # First account should automatically be primary
        added1 = await self.db.add_x_account(user_id, "@MainHandle")
        self.assertTrue(added1)

        # Second account is alt
        added2 = await self.db.add_x_account(user_id, "@AltAccount1", is_primary=False)
        self.assertTrue(added2)

        # Third account is another alt
        added3 = await self.db.add_x_account(user_id, "altaccount2", is_primary=False)
        self.assertTrue(added3)

        accounts = await self.db.get_user_x_accounts(user_id)
        self.assertEqual(len(accounts), 3)
        self.assertEqual(accounts[0]["x_username"], "mainhandle")
        self.assertEqual(accounts[0]["is_primary"], 1)
        self.assertEqual(accounts[1]["x_username"], "altaccount1")
        self.assertEqual(accounts[1]["is_primary"], 0)

        # Delete alt
        removed = await self.db.remove_x_account(user_id, "altaccount1")
        self.assertTrue(removed)
        accounts_after = await self.db.get_user_x_accounts(user_id)
        self.assertEqual(len(accounts_after), 2)

    async def test_post_queue_and_15_posts_assignment(self):
        """
        Simulate 20 users submitting posts.
        Verify that user 21 gets assigned the 15 posts submitted above their link.
        """
        # Create 20 previous users and posts
        for i in range(1, 21):
            uid = 1000 + i
            await self.db.upsert_user(uid, f"user{i}", f"User {i}")
            await self.db.add_x_account(uid, f"x_handle_{i}", is_primary=True)
            await self.db.add_post(
                telegram_id=uid,
                tweet_id=f"tweet_id_{i}",
                tweet_url=f"https://x.com/user{i}/status/{100000+i}",
                author_handle=f"user{i}"
            )

        # Now User 99 submits a post
        new_user_id = 9999
        await self.db.upsert_user(new_user_id, "newuser", "New User")
        await self.db.add_x_account(new_user_id, "newuser_x", is_primary=True)
        await self.db.add_x_account(new_user_id, "newuser_alt", is_primary=False)

        new_post_id = await self.db.add_post(
            telegram_id=new_user_id,
            tweet_id="new_user_tweet_id",
            tweet_url="https://x.com/newuser/status/999999",
            author_handle="newuser_x"
        )
        self.assertIsNotNone(new_post_id)

        # Fetch 15 posts above new_post_id
        posts_above = await self.db.get_posts_above(
            current_post_id=new_post_id,
            exclude_telegram_id=new_user_id,
            limit=15
        )

        self.assertEqual(len(posts_above), 15)
        # Verify they are ordered descending (posts 20 down to 6)
        self.assertEqual(posts_above[0]["tweet_id"], "tweet_id_20")
        self.assertEqual(posts_above[14]["tweet_id"], "tweet_id_6")

        # Create assignments
        assigned_ids = [p["id"] for p in posts_above]
        await self.db.create_assignments(new_user_id, new_post_id, assigned_ids)

        assignments = await self.db.get_assignments(new_post_id)
        self.assertEqual(len(assignments), 15)
        for a in assignments:
            self.assertEqual(a["is_verified"], 0)

        # Verify poster's TG username is populated in assignments
        self.assertEqual(assignments[0]["tg_username"], "user20")
        self.assertEqual(assignments[0]["author_handle"], "user20")

        # Verify formatting includes TG username of poster and submitter
        from bot.handlers.posts import format_assignment_message
        msg, v_count, t_count, is_comp = format_assignment_message(
            "https://x.com/newuser/status/999999",
            assignments,
            ["newuser_x"],
            submitter_mention="@newuser"
        )
        self.assertIn("Submitted by:</b> @newuser", msg)
        self.assertIn("TG: <b>@user20</b>", msg)

        # Test registering the same tweet multiple times (allowed without issue)
        second_post_id = await self.db.add_post(
            telegram_id=new_user_id,
            tweet_id="new_user_tweet_id",
            tweet_url="https://x.com/newuser/status/999999",
            author_handle="newuser_x"
        )
        self.assertIsNotNone(second_post_id)
        self.assertNotEqual(new_post_id, second_post_id)

        # Verify marking an assignment as verified
        first_assignment_id = assignments[0]["assignment_id"]
        await self.db.mark_assignment_verified(first_assignment_id, "newuser_alt")

        updated_assignments = await self.db.get_assignments(new_post_id)
        self.assertEqual(updated_assignments[0]["is_verified"], 1)
        self.assertEqual(updated_assignments[0]["verified_by_handle"], "newuser_alt")

    def test_sorsa_comment_matching_logic(self):
        client = SorsaClient(api_keys=["dummy_key"])
        
        # Test username extraction helper with various schemas
        sample_comment_1 = {
            "tweet_id": "123",
            "text": "Great project! LFG!",
            "author": {
                "username": "My_Alt_Account",
                "name": "Alt User"
            }
        }
        extracted1 = client._extract_username(sample_comment_1)
        self.assertEqual(extracted1, "my_alt_account")

        sample_comment_2 = {
            "tweet_id": "124",
            "text": "Nice tweet",
            "user": {
                "screen_name": "CryptoBull99"
            }
        }
        extracted2 = client._extract_username(sample_comment_2)
        self.assertEqual(extracted2, "cryptobull99")

    async def test_bulk_sorsa_api_keys(self):
        """Test bulk key addition, deduplication, status rotation, and resetting."""
        keys = ["key_alpha", "key_beta", "key_gamma", "key_alpha"]  # with 1 duplicate
        added, dups = await self.db.add_sorsa_keys(keys)
        self.assertEqual(added, 3)
        self.assertEqual(dups, 1)

        active_keys = await self.db.get_active_sorsa_keys()
        self.assertEqual(len(active_keys), 3)

        # Mark key_alpha as rate_limited
        await self.db.mark_sorsa_key_failed("key_alpha", "rate_limited", "HTTP 429")
        stats = await self.db.get_sorsa_keys_stats()
        self.assertEqual(stats["active"], 2)
        self.assertEqual(stats["rate_limited"], 1)

        # Reset all keys
        reset_count = await self.db.reset_all_sorsa_keys()
        self.assertEqual(reset_count, 1)
        stats_after = await self.db.get_sorsa_keys_stats()
        self.assertEqual(stats_after["active"], 3)
        self.assertEqual(stats_after["rate_limited"], 0)

        # Remove key
        removed = await self.db.remove_sorsa_key("key_beta")
        self.assertTrue(removed)
        stats_final = await self.db.get_sorsa_keys_stats()
        self.assertEqual(stats_final["total"], 2)

        # Mark key_gamma as invalid, then test delete_inactive_sorsa_keys
        await self.db.mark_sorsa_key_failed("key_gamma", "invalid", "HTTP 401")
        deleted_count = await self.db.delete_inactive_sorsa_keys()
        self.assertEqual(deleted_count, 1)
        stats_clean = await self.db.get_sorsa_keys_stats()
        self.assertEqual(stats_clean["total"], 1)
        self.assertEqual(stats_clean["active"], 1)
        self.assertEqual(stats_clean["invalid"], 0)


if __name__ == "__main__":
    unittest.main()
