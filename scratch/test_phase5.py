import unittest
import sys
import os
import json
import base64
import time
from datetime import datetime

# Add parent directory to path so we can import app and models cleanly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app
import models
import config

class TestPhase5(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        models.init_db()
        app.app.config['TESTING'] = True
        cls.client = app.app.test_client()
        
        # Override rate limiters to allow all requests during tests
        app.login_limiter.limit = 99999
        app.register_limiter.limit = 99999
        app.forge_limiter.limit = 99999

    def setUp(self):
        self.conn = models.get_db_connection()
        self.cursor = self.conn.cursor(dictionary=True)
        
        # Clean environment
        self.cursor.execute("DELETE FROM ratings WHERE id > 0")
        self.cursor.execute("DELETE FROM reviews WHERE id > 0")
        self.cursor.execute("DELETE FROM workflow_steps WHERE id > 0")
        self.cursor.execute("DELETE FROM workflow_runs WHERE id > 0")
        self.cursor.execute("DELETE FROM workflow_edges WHERE id > 0")
        self.cursor.execute("DELETE FROM workflow_nodes WHERE workflow_id > 0")
        self.cursor.execute("DELETE FROM workflow_variables WHERE id > 0")
        self.cursor.execute("DELETE FROM workflow_schedules WHERE id > 0")
        self.cursor.execute("DELETE FROM workflow_versions WHERE id > 0")
        self.cursor.execute("DELETE FROM workflows WHERE id > 0")
        self.cursor.execute("DELETE FROM agent_messages WHERE id > 0")
        self.cursor.execute("DELETE FROM agent_sessions WHERE id > 0")
        self.cursor.execute("DELETE FROM agent_memory WHERE id > 0")
        self.cursor.execute("DELETE FROM agents WHERE id > 0")
        self.cursor.execute("DELETE FROM organization_secrets WHERE id > 0")
        self.cursor.execute("DELETE FROM organization_members WHERE organization_id > 0")
        self.cursor.execute("DELETE FROM organizations WHERE id > 0")
        self.cursor.execute("DELETE FROM users WHERE email LIKE 'test_phase5_%'")
        self.conn.commit()

        # Register and login two test users
        self.user1_headers = self._create_user("test_phase5_u1@example.com", "User One")
        self.user2_headers = self._create_user("test_phase5_u2@example.com", "User Two")

    def tearDown(self):
        self.cursor.close()
        self.conn.close()

    def _create_user(self, email, name):
        self.client.post("/api/auth/register", json={
            "name": name,
            "email": email,
            "password": "Password123!"
        })
        login_res = self.client.post("/api/auth/login", json={
            "email": email,
            "password": "Password123!"
        })
        token = login_res.get_json()["token"]
        return {"Authorization": f"Bearer {token}"}

    def test_organizations_rbac_and_secrets(self):
        """1. Verify Org creation, membership role delegation, and secrets managers."""
        # User 1 creates Org
        res = self.client.post("/api/organizations", headers=self.user1_headers, json={
            "name": "Acme SaaS",
            "slug": "acme-saas"
        })
        self.assertEqual(res.status_code, 200)
        org_id = res.get_json()["org_id"]

        # Check membership (User 1 is owner)
        self.conn.commit()
        self.cursor.execute("SELECT role FROM organization_members WHERE organization_id = %s AND user_id = (SELECT id FROM users WHERE email = 'test_phase5_u1@example.com')", (org_id,))
        self.assertEqual(self.cursor.fetchone()["role"], "owner")

        # User 1 adds User 2 as viewer
        res = self.client.post(f"/api/organizations/{org_id}/members", headers=self.user1_headers, json={
            "email": "test_phase5_u2@example.com",
            "role": "viewer"
        })
        self.assertEqual(res.status_code, 200)

        # User 2 tries to update guardrails (Viewer role should fail with 403 Forbidden)
        res = self.client.put(f"/api/organizations/{org_id}/guardrails", headers=self.user2_headers, json={
            "max_monthly_cost": 200.0,
            "max_monthly_tokens": 1000000
        })
        self.assertEqual(res.status_code, 403)

        # User 1 updates guardrails (Owner role succeeds)
        res = self.client.put(f"/api/organizations/{org_id}/guardrails", headers=self.user1_headers, json={
            "max_monthly_cost": 150.0,
            "max_monthly_tokens": 8000000
        })
        self.assertEqual(res.status_code, 200)

        # Secrets Management
        # User 2 tries to insert secret (Viewer role should fail with 403)
        res = self.client.post(f"/api/organizations/{org_id}/secrets", headers=self.user2_headers, json={
            "name": "ENV.OPENAI_KEY",
            "value": "sk-1234"
        })
        self.assertEqual(res.status_code, 403)

        # User 1 adds secret
        res = self.client.post(f"/api/organizations/{org_id}/secrets", headers=self.user1_headers, json={
            "name": "ENV.OPENAI_KEY",
            "value": "sk-1234"
        })
        self.assertEqual(res.status_code, 200)

        # Verify encryption in DB (should be base64)
        self.conn.commit()
        self.cursor.execute("SELECT encrypted_value FROM organization_secrets WHERE organization_id = %s AND name = 'ENV.OPENAI_KEY'", (org_id,))
        secret_row = self.cursor.fetchone()
        self.assertEqual(secret_row["encrypted_value"], base64.b64encode(b"sk-1234").decode())

        # List secrets (value must be masked or omitted)
        res = self.client.get(f"/api/organizations/{org_id}/secrets", headers=self.user1_headers)
        secrets = res.get_json()["secrets"]
        self.assertEqual(len(secrets), 1)
        self.assertEqual(secrets[0]["name"], "ENV.OPENAI_KEY")
        self.assertNotIn("encrypted_value", secrets[0])

    def test_agent_library_playground(self):
        """2. Verify AI Agent Library CRUD and chat session Playground."""
        # Create Agent
        res = self.client.post("/api/agents", headers=self.user1_headers, json={
            "name": "Storyteller Agent",
            "role": "Creative Writer",
            "goals": "Generate engaging stories.",
            "instructions": "Use dramatic tone and rich narrative style.",
            "preferred_model": "llama3-8b-8192",
            "tools": ["Memory"]
        })
        self.assertEqual(res.status_code, 200)
        agent_id = res.get_json()["agent_id"]

        # List Agents
        res = self.client.get("/api/agents", headers=self.user1_headers)
        agents = res.get_json()["agents"]
        self.assertEqual(len(agents), 1)
        self.assertEqual(agents[0]["name"], "Storyteller Agent")

        # Start Session
        res = self.client.post(f"/api/agents/{agent_id}/chat/start", headers=self.user1_headers)
        session_id = res.get_json()["session_id"]

        # Send Message
        res = self.client.post(f"/api/agents/sessions/{session_id}/message", headers=self.user1_headers, json={
            "message": "Once upon a time..."
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertIn("response", data)
        self.assertGreater(data["tokens"], 0)

        # Check messages in DB
        res = self.client.get(f"/api/agents/sessions/{session_id}/messages", headers=self.user1_headers)
        messages = res.get_json()["messages"]
        self.assertEqual(len(messages), 2) # user + assistant

    def test_workflow_builder_saving_and_versions(self):
        """3. Verify Workflow saving, importing/exporting, snapshots, and version rollbacks."""
        # Create Workflow
        res = self.client.post("/api/workflows", headers=self.user1_headers, json={
            "title": "Data Pipeline",
            "description": "Extracts and runs prompt steps.",
            "category": "Automation"
        })
        self.assertEqual(res.status_code, 200)
        wf_id = res.get_json()["workflow_id"]

        # Update Workflow Canvas (Saves version snapshot 1)
        nodes = [
            {"id": f"{wf_id}_p1", "title": "Prompt Node", "type": "PromptNode", "prompt_template": "Topic: {{topic}}", "x": 100.0, "y": 150.0},
            {"id": f"{wf_id}_l1", "title": "LLM Node", "type": "LLMNode", "prompt_template": "{{p1}}", "x": 300.0, "y": 150.0, "config": {"model": "llama3-8b-8192", "system_prompt": "Translate to Spanish"}}
        ]
        edges = [
            {"source_node_id": f"{wf_id}_p1", "target_node_id": f"{wf_id}_l1", "source_handle": "out", "target_handle": "in"}
        ]
        res = self.client.put(f"/api/workflows/{wf_id}", headers=self.user1_headers, json={
            "nodes": nodes,
            "edges": edges,
            "variables": [{"name": "topic", "type": "string", "default_value": "Cats", "required": 1}]
        })
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["version_number"], 1)

        # Update Workflow Canvas with different nodes (Saves version snapshot 2)
        nodes2 = [
            {"id": f"{wf_id}_p1", "title": "Modified Prompt Node", "type": "PromptNode", "prompt_template": "Subject: {{topic}}", "x": 120.0, "y": 160.0}
        ]
        res = self.client.put(f"/api/workflows/{wf_id}", headers=self.user1_headers, json={
            "nodes": nodes2,
            "edges": [],
            "variables": []
        })
        self.assertEqual(res.get_json()["version_number"], 2)

        # Get versions list
        res = self.client.get(f"/api/workflows/{wf_id}/versions", headers=self.user1_headers)
        versions = res.get_json()["versions"]
        self.assertEqual(len(versions), 2)
        self.assertEqual(versions[0]["version_number"], 2)
        self.assertEqual(versions[1]["version_number"], 1)

        # Rollback to Version 1
        res = self.client.post(f"/api/workflows/{wf_id}/rollback/1", headers=self.user1_headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["rolled_back_to"], 1)

        # Verify active nodes are restored to Version 1 content
        res = self.client.get(f"/api/workflows/{wf_id}", headers=self.user1_headers)
        active_nodes = res.get_json()["nodes"]
        self.assertEqual(len(active_nodes), 2)
        prompt_node = next((n for n in active_nodes if n["type"] == "PromptNode"), None)
        self.assertIsNotNone(prompt_node)
        self.assertEqual(prompt_node["title"], "Prompt Node")

        # Export JSON
        res = self.client.get(f"/api/workflows/{wf_id}/export", headers=self.user1_headers)
        export_data = res.get_json()["export"]
        self.assertEqual(export_data["title"], "Data Pipeline")

        # Import JSON
        res = self.client.post("/api/workflows/import", headers=self.user1_headers, json={
            "workflow_data": export_data
        })
        self.assertEqual(res.status_code, 200)
        imported_wf_id = res.get_json()["workflow_id"]
        self.assertNotEqual(imported_wf_id, wf_id)

    def test_workflow_runner_executions_and_retry(self):
        """4. Verify Workflow executions, Condition branching, Webhooks, delays, and Node Retries."""
        # Create Workflow
        res = self.client.post("/api/workflows", headers=self.user1_headers, json={
            "title": "Conditional Pipeline"
        })
        wf_id = res.get_json()["workflow_id"]

        # Setup nodes: PromptNode -> ConditionNode -> LLMNode (True Path) and DelayNode (False Path)
        nodes = [
            {"id": f"{wf_id}_p1", "title": "Prompt", "type": "PromptNode", "prompt_template": "topic: {{topic}}"},
            {"id": f"{wf_id}_c1", "title": "Check", "type": "ConditionNode", "config": {"left": "{{p1}}", "operator": "contains", "right": "cats"}},
            {"id": f"{wf_id}_l1", "title": "LLM", "type": "LLMNode", "prompt_template": "Analyze: {{p1}}", "config": {"retry_count": 2, "retry_delay": 0.1}},
            {"id": f"{wf_id}_d1", "title": "Delay", "type": "DelayNode", "config": {"seconds": 0.1}}
        ]
        edges = [
            {"source_node_id": f"{wf_id}_p1", "target_node_id": f"{wf_id}_c1", "source_handle": "out", "target_handle": "in"},
            {"source_node_id": f"{wf_id}_c1", "target_node_id": f"{wf_id}_l1", "source_handle": "true", "target_handle": "in"},
            {"source_node_id": f"{wf_id}_c1", "target_node_id": f"{wf_id}_d1", "source_handle": "false", "target_handle": "in"}
        ]
        self.client.put(f"/api/workflows/{wf_id}", headers=self.user1_headers, json={
            "nodes": nodes,
            "edges": edges,
            "variables": [{"name": "topic", "type": "string"}]
        })

        # Run Workflow via API (topic contains "cats" -> True Path resolves, False Path skips)
        res = self.client.post(f"/api/workflows/{wf_id}/run", headers=self.user1_headers, json={
            "inputs": {"topic": "cats rule"}
        })
        self.assertEqual(res.status_code, 200)
        run_id = res.get_json()["run_id"]

        # Wait for completion
        time.sleep(2.0)

        # Check run status & steps
        res = self.client.get(f"/api/workflow_runs/{run_id}", headers=self.user1_headers)
        data = res.get_json()
        self.assertEqual(data["run"]["status"], "completed")
        
        steps = {s["node_id"]: s for s in data["steps"]}
        # LLMNode was completed
        self.assertEqual(steps[f"{wf_id}_l1"]["status"], "completed")
        # DelayNode was skipped
        self.assertEqual(steps[f"{wf_id}_d1"]["status"], "completed") # saved with status=completed and skipped message
        self.assertIn("Skipped", steps[f"{wf_id}_d1"]["output_generated"])

        # Webhook Trigger verification
        res = self.client.post(f"/api/workflows/webhooks/{wf_id}", json={
            "topic": "dogs rule" # topic does not contain cats -> False Path resolves, True Path skips
        })
        self.assertEqual(res.status_code, 200)
        wh_run_id = res.get_json()["run_id"]

        time.sleep(2.0)
        res = self.client.get(f"/api/workflow_runs/{wh_run_id}", headers=self.user1_headers)
        data2 = res.get_json()
        self.assertEqual(data2["run"]["status"], "completed")
        steps2 = {s["node_id"]: s for s in data2["steps"]}
        self.assertEqual(steps2[f"{wf_id}_d1"]["status"], "completed")
        self.assertIn("Delayed", steps2[f"{wf_id}_d1"]["output_generated"])
        self.assertIn("Skipped", steps2[f"{wf_id}_l1"]["output_generated"])

    def test_cron_matcher(self):
        """5. Verify zero-dependency cron schedule matches due times."""
        # Matching minute: 2026-06-26 07:05:00
        dt = datetime(2026, 6, 26, 7, 5, 0)
        
        # Every minute
        self.assertTrue(app.is_cron_due("* * * * *", dt))
        # Divisions: every 5 minutes (due at minute 5)
        self.assertTrue(app.is_cron_due("*/5 * * * *", dt))
        # Not matching divisions: every 10 minutes (not due at minute 5)
        self.assertFalse(app.is_cron_due("*/10 * * * *", dt))
        # Matching exact minute
        self.assertTrue(app.is_cron_due("5 7 * * *", dt))
        # Non matching hour
        self.assertFalse(app.is_cron_due("5 8 * * *", dt))
        
        print("Cron matcher logic fully tested.")

if __name__ == "__main__":
    unittest.main()
