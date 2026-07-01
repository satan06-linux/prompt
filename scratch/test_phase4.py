import unittest
import sys
import os
from datetime import datetime, timedelta

# Add parent directory to path so we can import app and models cleanly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app
import models
import config

class TestPhase4(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Initialize/verify database
        models.init_db()
        # Enable app testing mode
        app.app.config['TESTING'] = True
        cls.client = app.app.test_client()
        
        # Override rate limiters to allow all requests during tests
        app.login_limiter.limit = 99999
        app.register_limiter.limit = 99999
        app.forge_limiter.limit = 99999

    def setUp(self):
        self.conn = models.get_db_connection()
        self.cursor = self.conn.cursor(dictionary=True)
        # Clear out existing test users/prompts to have a clean environment
        self.cursor.execute("DELETE FROM notifications WHERE id > 0")
        self.cursor.execute("DELETE FROM reports WHERE id > 0")
        self.cursor.execute("DELETE FROM prompt_likes WHERE user_id > 0 OR prompt_id > 0")
        self.cursor.execute("DELETE FROM prompt_views WHERE prompt_id > 0")
        self.cursor.execute("DELETE FROM prompts WHERE input_text LIKE 'test_phase4_%' OR input_text LIKE 'Rate limit%' OR input_text LIKE 'Like test%' OR input_text LIKE 'Report test%' OR input_text LIKE 'Notification test%' OR input_text IN ('P1', 'P2') OR input_text LIKE 'UUID prompt%' OR input_text LIKE 'View test%' OR input_text = 'Prompt to delete'")
        self.cursor.execute("DELETE FROM users WHERE email LIKE 'test_phase4_%'")
        self.conn.commit()

    def tearDown(self):
        try:
            self.cursor.execute("DELETE FROM notifications WHERE id > 0")
            self.cursor.execute("DELETE FROM reports WHERE id > 0")
            self.cursor.execute("DELETE FROM prompt_likes WHERE user_id > 0 OR prompt_id > 0")
            self.cursor.execute("DELETE FROM prompt_views WHERE prompt_id > 0")
            self.cursor.execute("DELETE FROM prompts WHERE input_text LIKE 'test_phase4_%' OR input_text LIKE 'Rate limit%' OR input_text LIKE 'Like test%' OR input_text LIKE 'Report test%' OR input_text LIKE 'Notification test%' OR input_text IN ('P1', 'P2') OR input_text LIKE 'UUID prompt%' OR input_text LIKE 'View test%' OR input_text = 'Prompt to delete'")
            self.cursor.execute("DELETE FROM users WHERE email LIKE 'test_phase4_%'")
            self.conn.commit()
        except Exception:
            pass
        self.cursor.close()
        self.conn.close()

    def test_username_collision_handling(self):
        """1. Safe username generation and collision handling (generate 10 duplicate names and ensure all usernames are unique)"""
        usernames = []
        for i in range(10):
            email = f"test_phase4_user_{i}@example.com"
            res = self.client.post("/api/auth/register", json={
                "name": "Test User",
                "email": email,
                "password": "Password123!"
            })
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertTrue(data["success"])
            
            # Fetch the generated username from DB (commit to start new transaction view)
            self.conn.commit()
            self.cursor.execute("SELECT username FROM users WHERE email = %s", (email,))
            u = self.cursor.fetchone()
            usernames.append(u["username"])
            
        # Ensure all 10 usernames are unique
        self.assertEqual(len(set(usernames)), 10)
        print("Username collision test passed:", usernames)

    def test_soft_deletes(self):
        """2. Soft deletes (delete prompt, verify it is excluded from search/gallery/feeds but stays in DB)"""
        email = "test_phase4_creator_softdelete@example.com"
        self.client.post("/api/auth/register", json={
            "name": "Soft Delete Creator",
            "email": email,
            "password": "Password123!"
        })
        login_res = self.client.post("/api/auth/login", json={
            "email": email,
            "password": "Password123!"
        })
        token = login_res.get_json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create a prompt
        prompt_res = self.client.post("/api/save-prompt", json={
            "input_text": "Prompt to delete",
            "category": "Code",
            "mcq_questions": {},
            "mcq_answers": {},
            "generated_prompt": "A generated code prompt",
            "quality_score": 95,
            "target_model": "llama3",
            "optimization_style": "code"
        }, headers=headers)
        prompt_id = prompt_res.get_json()["prompt_id"]

        # Publish it so it is visible in the public gallery
        pub_res = self.client.post("/api/prompts/publish", json={
            "prompt_id": prompt_id,
            "visibility": "public"
        }, headers=headers)
        self.assertTrue(pub_res.get_json()["success"])

        # Verify it is in the gallery
        gallery_res = self.client.get("/api/community/prompts")
        prompts_in_gallery = [p["id"] for p in gallery_res.get_json()["prompts"]]
        self.assertIn(prompt_id, prompts_in_gallery)

        # Soft delete the prompt
        del_res = self.client.post("/api/prompts/delete", json={
            "prompt_id": prompt_id
        }, headers=headers)
        self.assertTrue(del_res.get_json()["success"])

        # Verify it is EXCLUDED from gallery
        gallery_res2 = self.client.get("/api/community/prompts")
        prompts_in_gallery2 = [p["id"] for p in gallery_res2.get_json()["prompts"]]
        self.assertNotIn(prompt_id, prompts_in_gallery2)

        # Verify it is STILL in the database (deleted_at is NOT NULL)
        self.conn.commit()
        self.cursor.execute("SELECT deleted_at FROM prompts WHERE id = %s", (prompt_id,))
        p = self.cursor.fetchone()
        self.assertIsNotNone(p)
        self.assertIsNotNone(p["deleted_at"])
        print("Soft delete test passed.")

    def test_publishing_rate_limit(self):
        """3. Publishing limit enforcement (10 published per hour maximum)"""
        email = "test_phase4_rate_limiter@example.com"
        self.client.post("/api/auth/register", json={
            "name": "Limit Creator",
            "email": email,
            "password": "Password123!"
        })
        login_res = self.client.post("/api/auth/login", json={
            "email": email,
            "password": "Password123!"
        })
        token = login_res.get_json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create 11 prompts
        prompt_ids = []
        for i in range(11):
            prompt_res = self.client.post("/api/save-prompt", json={
                "input_text": f"Rate limit prompt {i}",
                "category": "Code",
                "mcq_questions": {},
                "mcq_answers": {},
                "generated_prompt": f"Generated prompt {i}"
            }, headers=headers)
            prompt_ids.append(prompt_res.get_json()["prompt_id"])

        # Try to publish all 11 prompts
        success_count = 0
        blocked_on_11th = False
        for pid in prompt_ids:
            pub_res = self.client.post("/api/prompts/publish", json={
                "prompt_id": pid,
                "visibility": "public"
            }, headers=headers)
            res_data = pub_res.get_json()
            if res_data["success"]:
                success_count += 1
            else:
                if "hourly limit" in res_data.get("error", "").lower() or pub_res.status_code == 429:
                    blocked_on_11th = True

        self.assertEqual(success_count, 10)
        self.assertTrue(blocked_on_11th)
        print("Publishing hourly rate limit test passed.")

    def test_unique_daily_views_tracking(self):
        """4. Unique daily views tracking in `prompt_views`"""
        email_creator = "test_phase4_view_creator@example.com"
        self.client.post("/api/auth/register", json={
            "name": "View Creator",
            "email": email_creator,
            "password": "Password123!"
        })
        login_res = self.client.post("/api/auth/login", json={
            "email": email_creator,
            "password": "Password123!"
        })
        creator_token = login_res.get_json()["token"]
        headers = {"Authorization": f"Bearer {creator_token}"}
        
        # Save a prompt and publish
        prompt_res = self.client.post("/api/save-prompt", json={
            "input_text": "View test prompt",
            "category": "Code",
            "mcq_questions": {},
            "mcq_answers": {},
            "generated_prompt": "A prompt to view"
        }, headers=headers)
        prompt_id = prompt_res.get_json()["prompt_id"]

        pub_res = self.client.post("/api/prompts/publish", json={
            "prompt_id": prompt_id,
            "visibility": "public"
        }, headers=headers)
        share_uuid = pub_res.get_json()["share_uuid"]

        # View twice as the same client (hit HTML page route which increments view)
        res1 = self.client.get(f"/share/{share_uuid}", headers={"X-Forwarded-For": "1.1.1.1"})
        self.assertEqual(res1.status_code, 200)

        res2 = self.client.get(f"/share/{share_uuid}", headers={"X-Forwarded-For": "1.1.1.1"})
        self.assertEqual(res2.status_code, 200)

        # Query views from DB
        self.conn.commit()
        self.cursor.execute("SELECT views FROM prompts WHERE id = %s", (prompt_id,))
        p = self.cursor.fetchone()
        self.assertEqual(p["views"], 1)

        self.cursor.execute("SELECT COUNT(*) AS total FROM prompt_views WHERE prompt_id = %s", (prompt_id,))
        pv_count = self.cursor.fetchone()["total"]
        self.assertEqual(pv_count, 1)
        print("Unique daily views test passed.")

    def test_atomic_likes_forks_caches(self):
        """5. Atomic like/fork caches updates in `prompts` table"""
        email_c = "test_phase4_like_creator@example.com"
        email_u = "test_phase4_like_user@example.com"
        self.client.post("/api/auth/register", json={"name": "LC", "email": email_c, "password": "Password123!"})
        self.client.post("/api/auth/register", json={"name": "LU", "email": email_u, "password": "Password123!"})
        
        login_c = self.client.post("/api/auth/login", json={"email": email_c, "password": "Password123!"})
        login_u = self.client.post("/api/auth/login", json={"email": email_u, "password": "Password123!"})
        token_c = login_c.get_json()["token"]
        token_u = login_u.get_json()["token"]

        # Save and publish prompt
        p_res = self.client.post("/api/save-prompt", json={
            "input_text": "Like test prompt",
            "category": "Code",
            "mcq_questions": {},
            "mcq_answers": {},
            "generated_prompt": "A prompt to like"
        }, headers={"Authorization": f"Bearer {token_c}"})
        prompt_id = p_res.get_json()["prompt_id"]

        self.client.post("/api/prompts/publish", json={"prompt_id": prompt_id, "visibility": "public"}, headers={"Authorization": f"Bearer {token_c}"})

        # Check initial like_count
        self.conn.commit()
        self.cursor.execute("SELECT like_count FROM prompts WHERE id = %s", (prompt_id,))
        self.assertEqual(self.cursor.fetchone()["like_count"], 0)

        # Like the prompt
        like_res = self.client.post(f"/api/prompts/{prompt_id}/like", headers={"Authorization": f"Bearer {token_u}"})
        self.assertTrue(like_res.get_json()["success"])

        # Check like_count has incremented to 1
        self.conn.commit()
        self.cursor.execute("SELECT like_count FROM prompts WHERE id = %s", (prompt_id,))
        self.assertEqual(self.cursor.fetchone()["like_count"], 1)

        # Unlike the prompt
        unlike_res = self.client.post(f"/api/prompts/{prompt_id}/unlike", headers={"Authorization": f"Bearer {token_u}"})
        self.assertTrue(unlike_res.get_json()["success"])

        # Check like_count has decremented back to 0
        self.conn.commit()
        self.cursor.execute("SELECT like_count FROM prompts WHERE id = %s", (prompt_id,))
        self.assertEqual(self.cursor.fetchone()["like_count"], 0)

        # Fork the prompt
        fork_res = self.client.post(f"/api/prompts/{prompt_id}/fork", headers={"Authorization": f"Bearer {token_u}"})
        self.assertTrue(fork_res.get_json()["success"])

        # Check fork_count has incremented to 1
        self.conn.commit()
        self.cursor.execute("SELECT fork_count FROM prompts WHERE id = %s", (prompt_id,))
        self.assertEqual(self.cursor.fetchone()["fork_count"], 1)
        print("Atomic likes/forks caches test passed.")

    def test_duplicate_reports_protection(self):
        """6. Unique constraint on prompt reports (duplicate reports are rejected)"""
        email_c = "test_phase4_rep_c@example.com"
        email_u = "test_phase4_rep_u@example.com"
        self.client.post("/api/auth/register", json={"name": "RC", "email": email_c, "password": "Password123!"})
        self.client.post("/api/auth/register", json={"name": "RU", "email": email_u, "password": "Password123!"})
        
        login_c = self.client.post("/api/auth/login", json={"email": email_c, "password": "Password123!"})
        login_u = self.client.post("/api/auth/login", json={"email": email_u, "password": "Password123!"})
        token_c = login_c.get_json()["token"]
        token_u = login_u.get_json()["token"]

        p_res = self.client.post("/api/save-prompt", json={
            "input_text": "Report test prompt",
            "category": "Code",
            "mcq_questions": {},
            "mcq_answers": {},
            "generated_prompt": "A prompt to report"
        }, headers={"Authorization": f"Bearer {token_c}"})
        prompt_id = p_res.get_json()["prompt_id"]

        self.client.post("/api/prompts/publish", json={"prompt_id": prompt_id, "visibility": "public"}, headers={"Authorization": f"Bearer {token_c}"})

        # Submit first report
        rep_res1 = self.client.post(f"/api/prompts/{prompt_id}/report", json={
            "reason": "Spam",
            "comment": "First report comment"
        }, headers={"Authorization": f"Bearer {token_u}"})
        self.assertTrue(rep_res1.get_json()["success"])

        # Submit second report (should fail due to duplicate report protection)
        rep_res2 = self.client.post(f"/api/prompts/{prompt_id}/report", json={
            "reason": "Abuse",
            "comment": "Second report comment"
        }, headers={"Authorization": f"Bearer {token_u}"})
        self.assertFalse(rep_res2.get_json()["success"])
        self.assertIn("already reported", rep_res2.get_json()["error"].lower())
        print("Duplicate reports protection test passed.")

    def test_notification_deduplication(self):
        """7. Notifications deduplication (unlike deletes unread notification)"""
        email_c = "test_phase4_notif_c@example.com"
        email_u = "test_phase4_notif_u@example.com"
        self.client.post("/api/auth/register", json={"name": "NC", "email": email_c, "password": "Password123!"})
        self.client.post("/api/auth/register", json={"name": "NU", "email": email_u, "password": "Password123!"})
        
        login_c = self.client.post("/api/auth/login", json={"email": email_c, "password": "Password123!"})
        login_u = self.client.post("/api/auth/login", json={"email": email_u, "password": "Password123!"})
        token_c = login_c.get_json()["token"]
        token_u = login_u.get_json()["token"]

        p_res = self.client.post("/api/save-prompt", json={
            "input_text": "Notification test prompt",
            "category": "Code",
            "mcq_questions": {},
            "mcq_answers": {},
            "generated_prompt": "A prompt for notifications"
        }, headers={"Authorization": f"Bearer {token_c}"})
        prompt_id = p_res.get_json()["prompt_id"]

        self.client.post("/api/prompts/publish", json={"prompt_id": prompt_id, "visibility": "public"}, headers={"Authorization": f"Bearer {token_c}"})

        # User likes the prompt -> should generate notification for creator
        self.client.post(f"/api/prompts/{prompt_id}/like", headers={"Authorization": f"Bearer {token_u}"})
        
        # Verify notification is present
        self.conn.commit()
        self.cursor.execute("SELECT COUNT(*) AS total FROM notifications WHERE type = 'like' AND prompt_id = %s", (prompt_id,))
        self.assertEqual(self.cursor.fetchone()["total"], 1)

        # User unlikes the prompt -> should remove the like notification
        self.client.post(f"/api/prompts/{prompt_id}/unlike", headers={"Authorization": f"Bearer {token_u}"})

        # Verify notification is deleted
        self.conn.commit()
        self.cursor.execute("SELECT COUNT(*) AS total FROM notifications WHERE type = 'like' AND prompt_id = %s", (prompt_id,))
        self.assertEqual(self.cursor.fetchone()["total"], 0)
        print("Notification deduplication test passed.")

    def test_trending_score_algorithm_sorting(self):
        """8. Trending score algorithm sorting verification"""
        email = "test_phase4_trend@example.com"
        self.client.post("/api/auth/register", json={"name": "TrendCreator", "email": email, "password": "Password123!"})
        login_res = self.client.post("/api/auth/login", json={"email": email, "password": "Password123!"})
        token = login_res.get_json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create two public prompts
        p1_res = self.client.post("/api/save-prompt", json={"input_text": "P1", "category": "Code", "mcq_questions": {}, "mcq_answers": {}, "generated_prompt": "GP1", "quality_score": 90}, headers=headers)
        p2_res = self.client.post("/api/save-prompt", json={"input_text": "P2", "category": "Code", "mcq_questions": {}, "mcq_answers": {}, "generated_prompt": "GP2", "quality_score": 80}, headers=headers)
        pid1 = p1_res.get_json()["prompt_id"]
        pid2 = p2_res.get_json()["prompt_id"]

        self.client.post("/api/prompts/publish", json={"prompt_id": pid1, "visibility": "public"}, headers=headers)
        self.client.post("/api/prompts/publish", json={"prompt_id": pid2, "visibility": "public"}, headers=headers)

        # Manually manipulate atomic counts/views for test:
        self.cursor.execute("UPDATE prompts SET like_count = 10, fork_count = 5, views = 100 WHERE id = %s", (pid1,))
        self.cursor.execute("UPDATE prompts SET like_count = 5, fork_count = 2, views = 20 WHERE id = %s", (pid2,))
        self.conn.commit()

        # Fetch trending prompts from API
        res = self.client.get("/api/community/prompts?sort=trending")
        prompts = res.get_json()["prompts"]
        
        # Verify Prompt 1 comes before Prompt 2 in the trending feed
        p_ids = [p["id"] for p in prompts]
        idx1 = p_ids.index(pid1)
        idx2 = p_ids.index(pid2)
        self.assertLess(idx1, idx2)
        print("Trending score sorting algorithm test passed.")

    def test_share_uuid_uniqueness(self):
        """9. Share UUID uniqueness (publish 50 prompts, confirm all `share_uuid` are unique and 12 characters)"""
        email = "test_phase4_uuid@example.com"
        self.client.post("/api/auth/register", json={"name": "UUIDCreator", "email": email, "password": "Password123!"})
        login_res = self.client.post("/api/auth/login", json={"email": email, "password": "Password123!"})
        token = login_res.get_json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create 50 prompts
        uuids = []
        for i in range(50):
            p_res = self.client.post("/api/save-prompt", json={
                "input_text": f"UUID prompt {i}",
                "category": "Code",
                "mcq_questions": {},
                "mcq_answers": {},
                "generated_prompt": f"GP {i}"
            }, headers=headers)
            pid = p_res.get_json()["prompt_id"]

            pub_res = self.client.post("/api/prompts/publish", json={"prompt_id": pid, "visibility": "public"}, headers=headers)
            suuid = pub_res.get_json()["share_uuid"]
            uuids.append(suuid)

            # Backdate this prompt's published_at to bypass the hourly limit of 10
            self.cursor.execute("UPDATE prompts SET published_at = NOW() - INTERVAL 2 HOUR WHERE id = %s", (pid,))
            self.conn.commit()

        # Check lengths
        for u in uuids:
            self.assertEqual(len(u), 12)
        
        # Check uniqueness
        self.assertEqual(len(set(uuids)), 50)
        print("Share UUID uniqueness test passed.")

    def test_transaction_rollback(self):
        """10. Transaction rollback test: Simulate a failure during a multi-step operation and verify no partial database updates remain."""
        conn = models.get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            # Check current state of users table
            cursor.execute("SELECT COUNT(*) AS total FROM users WHERE email = 'test_phase4_rollback@example.com'")
            initial_count = cursor.fetchone()["total"]
            
            # Start multi-step insert
            cursor.execute("INSERT INTO users (name, email, password_hash, role) VALUES (%s, %s, %s, %s)",
                           ("Rollback User", "test_phase4_rollback@example.com", "hash", "user"))
            
            # Intentionally execute a faulty query that fails (user_id -999 violates foreign key)
            cursor.execute("INSERT INTO prompts (user_id, input_text, category, mcq_questions, mcq_answers, generated_prompt, quality_score) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                           (-999, None, "Code", "{}", "{}", "Prompt content", 100))
            
            conn.commit()
        except Exception as e:
            conn.rollback()
            print("Successfully caught intentional exception and rolled back transaction:", str(e))
        
        # Verify that the first insert was rolled back and is not in the database
        cursor.execute("SELECT COUNT(*) AS total FROM users WHERE email = 'test_phase4_rollback@example.com'")
        final_count = cursor.fetchone()["total"]
        self.assertEqual(initial_count, final_count)
        
        cursor.close()
        conn.close()
        print("Transaction rollback verification test passed.")

if __name__ == "__main__":
    unittest.main()
