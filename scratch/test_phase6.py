import unittest
import sys
import os
import json
import time
import struct
from datetime import datetime

# Add parent directory to path so we can import app and models cleanly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app
import models
import config
from services.config_service import ConfigService
from services.router_service import RouterService
from services.vector_service import MySQLVectorStore
from services.embedding_service import EmbeddingService
from services.sandbox_service import SandboxService
from services.event_bus import event_bus
from services.plugin_sdk import PluginSDK, NodeExecutionContext
from services.streaming_service import StreamingService
from services.mcp_service import MCPService

class TestPhase6(unittest.TestCase):
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
        self.cursor.execute("DELETE FROM workflow_run_evaluations WHERE id > 0")
        self.cursor.execute("DELETE FROM observability_traces WHERE id > 0")
        self.cursor.execute("DELETE FROM memory_scopes WHERE id > 0")
        self.cursor.execute("DELETE FROM generated_artifacts WHERE id > 0")
        self.cursor.execute("DELETE FROM workflow_contexts WHERE id > 0")
        self.cursor.execute("DELETE FROM knowledge_chunks WHERE id > 0")
        self.cursor.execute("DELETE FROM knowledge_jobs WHERE id > 0")
        self.cursor.execute("DELETE FROM knowledge_documents WHERE id > 0")
        self.cursor.execute("DELETE FROM knowledge_bases WHERE id > 0")
        self.cursor.execute("DELETE FROM prompt_registry_versions WHERE id > 0")
        self.cursor.execute("DELETE FROM prompt_registry WHERE id > 0")
        self.cursor.execute("DELETE FROM model_routers WHERE id > 0")
        self.cursor.execute("DELETE FROM models WHERE id > 0")
        self.cursor.execute("DELETE FROM providers WHERE id > 0")
        self.cursor.execute("DELETE FROM workflow_steps WHERE id > 0")
        self.cursor.execute("DELETE FROM workflow_runs WHERE id > 0")
        self.cursor.execute("DELETE FROM workflows WHERE id > 0")
        self.cursor.execute("DELETE FROM users WHERE email LIKE 'test_phase6_%'")
        self.conn.commit()

        # Register and login test user
        self.user_headers = self._create_user("test_phase6_user@example.com", "Phase 6 Tester")
        
        # Query real user id to satisfy foreign key constraints
        self.cursor.execute("SELECT id FROM users WHERE email = 'test_phase6_user@example.com'")
        self.test_user_id = self.cursor.fetchone()["id"]

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

    def test_prompt_registry_crud_and_rollback(self):
        """1. Verify Git-style prompt registry version snapshots and rollbacks."""
        # Create prompt registry entry
        res = self.client.post("/api/prompts/registry", headers=self.user_headers, json={
            "title": "Enterprise Summary",
            "description": "Summarizes documents with strict constraints.",
            "category": "writing",
            "prompt_template": "Summarize this: {text}",
            "system_prompt": "You are a summarizing expert."
        })
        self.assertEqual(res.status_code, 200)
        prompt_id = res.get_json()["prompt_id"]
        self.assertEqual(res.get_json()["version"], 1)

        # Update prompt template (v2)
        res = self.client.put(f"/api/prompts/registry/{prompt_id}", headers=self.user_headers, json={
            "prompt_template": "Summarize this beautifully: {text}",
            "system_prompt": "You are a master summary writer."
        })
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["version"], 2)

        # Rollback back to version 1
        res = self.client.post(f"/api/prompts/registry/{prompt_id}/rollback/1", headers=self.user_headers)
        self.assertEqual(res.status_code, 200)
        new_ver = res.get_json()["version"]
        self.assertEqual(new_ver, 3)

        # Check prompt details to verify content matches v1
        res = self.client.get(f"/api/prompts/registry/{prompt_id}", headers=self.user_headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        versions = data["versions"]
        
        # Latest version should be 3 and template should match version 1
        latest_version = [v for v in versions if v["version_number"] == 3][0]
        self.assertEqual(latest_version["prompt_template"], "Summarize this: {text}")
        self.assertEqual(latest_version["system_prompt"], "You are a summarizing expert.")

    def test_model_router_mapping(self):
        """2. Verify Task Routing rules selection based on task type preferences."""
        # Insert provider
        self.cursor.execute(
            "INSERT INTO providers (name, enabled) VALUES ('openai', 1)"
        )
        provider_id = self.cursor.lastrowid
        
        # Insert models
        self.cursor.execute(
            "INSERT INTO models (provider_id, model_name, model_type, enabled) VALUES (%s, 'gpt-4o', 'llm', 1)",
            (provider_id,)
        )
        gpt4_id = self.cursor.lastrowid
        
        self.cursor.execute(
            "INSERT INTO models (provider_id, model_name, model_type, enabled) VALUES (%s, 'gpt-4o-mini', 'llm', 1)",
            (provider_id,)
        )
        gpt4_mini_id = self.cursor.lastrowid

        # Insert model router config
        self.cursor.execute(
            """
            INSERT INTO model_routers (organization_id, task_type, preferred_model_id, fallback_model_id, enabled)
            VALUES (NULL, 'coding', %s, %s, 1)
            """,
            (gpt4_id, gpt4_mini_id)
        )
        self.conn.commit()

        # Check router selection
        route = RouterService.route_task("coding", organization_id=None)
        self.assertEqual(route["provider"], "openai")
        self.assertEqual(route["model"], "gpt-4o")

        # Fallback to local default if route not configured
        route_fallback = RouterService.route_task("writing", organization_id=None)
        self.assertEqual(route_fallback["provider"], "groq")
        self.assertEqual(route_fallback["model"], "llama3-8b-8192")

    def test_rag_ingest_and_similarity_search(self):
        """3. Verify text overlapping chunks and MySQL Packed float blob vector search."""
        # Setup Knowledge Base
        self.cursor.execute(
            "INSERT INTO knowledge_bases (user_id, title) VALUES (%s, 'Engineering Handbook')",
            (self.test_user_id,)
        )
        kb_id = self.cursor.lastrowid
        
        self.cursor.execute(
            "INSERT INTO knowledge_documents (kb_id, filename, filetype, filesize) VALUES (%s, 'handbook.txt', 'text/plain', 100)",
            (kb_id,)
        )
        doc_id = self.cursor.lastrowid

        # Add chunk text starting directly with keywords to align positions with the local hash embedding
        chunk1 = "antigravity compiler converts code directly to levitation commands."
        chunk2 = "gravity generator operates at 50Hz frequency by default."
        
        v1 = EmbeddingService.embed(chunk1, provider_name="local")
        v2 = EmbeddingService.embed(chunk2, provider_name="local")

        # Insert chunks with serialized vectors using struct.pack directly
        v1_blob = struct.pack(f"{len(v1)}f", *v1)
        v2_blob = struct.pack(f"{len(v2)}f", *v2)

        self.cursor.execute(
            "INSERT INTO knowledge_chunks (doc_id, chunk_index, chunk_text, embedding_vector) VALUES (%s, 1, %s, %s)",
            (doc_id, chunk1, v1_blob)
        )
        self.cursor.execute(
            "INSERT INTO knowledge_chunks (doc_id, chunk_index, chunk_text, embedding_vector) VALUES (%s, 2, %s, %s)",
            (doc_id, chunk2, v2_blob)
        )
        self.conn.commit()

        # Query search matches
        query_vector = EmbeddingService.embed("antigravity compiler", provider_name="local")
        vector_store = MySQLVectorStore()
        results = vector_store.similarity_search(kb_id, query_vector, top_k=2)

        self.assertGreater(len(results), 0)
        self.assertEqual(results[0]["doc_id"], doc_id)
        # The first chunk should match the query better than the second
        self.assertEqual(results[0]["text"], chunk1)
        self.assertGreater(results[0]["score"], results[1]["score"])

    def test_python_sandbox_constraints(self):
        """4. Verify process-level timeouts, blocked imports, and outputs limit."""
        # 1. Blocked module check (set timeout longer to avoid startup delays on slow hardware)
        code_blocked = "import os\nprint(os.listdir('.'))"
        res_blocked = SandboxService.execute_code(code_blocked, timeout_sec=15.0)
        self.assertFalse(res_blocked["success"])
        self.assertIn("blocked", res_blocked["error"])

        # 2. Timeout check (Infinite Loop)
        code_timeout = "import time\nwhile True:\n    pass"
        res_timeout = SandboxService.execute_code(code_timeout, timeout_sec=0.5)
        self.assertFalse(res_timeout["success"])
        self.assertIn("timed out", res_timeout["error"])

        # 3. Whitelisted modules execution
        code_ok = "import math\nresult = math.sqrt(16)\nprint('Square root resolved')"
        res_ok = SandboxService.execute_code(code_ok, timeout_sec=15.0)
        self.assertTrue(res_ok["success"])
        self.assertIn("Square root resolved", res_ok["stdout"])
        self.assertEqual(res_ok["outputs"].get("result"), 4.0)

    def test_sql_node_constraints(self):
        """5. Verify SQLNode blocks modifications (UPDATE/DELETE) and permits SELECT queries."""
        # Create a mock workflow and run
        self.cursor.execute("INSERT INTO workflows (title, user_id) VALUES ('SQL Workflow', %s)", (self.test_user_id,))
        wf_id = self.cursor.lastrowid
        self.cursor.execute("INSERT INTO workflow_runs (workflow_id, user_id, status, inputs) VALUES (%s, %s, 'queued', '{}')", (wf_id, self.test_user_id))
        run_id = self.cursor.lastrowid
        
        # Enforce SELECT allowed (must supply 'title' for workflow_nodes)
        sql_allowed = "SELECT id, email FROM users LIMIT 1"
        self.cursor.execute(
            "INSERT INTO workflow_nodes (id, workflow_id, type, title, config_json) VALUES ('node_1', %s, 'SQLNode', 'Allowed Query', %s)",
            (wf_id, json.dumps({"query": sql_allowed}))
        )
        self.conn.commit()

        # Simulate executing the node via workflow runner or direct verification
        runner = app.WorkflowRunner(run_id)
        # Mock inputs/outputs
        runner.nodes = {'node_1': {"id": "node_1", "type": "SQLNode", "title": "Allowed Query", "config_json": json.dumps({"query": sql_allowed}), "workflow_id": wf_id}}
        runner.outputs = {}
        runner.inputs = {}
        runner.statuses = {'node_1': 'running'}
        runner.run_node('node_1')
        
        self.assertEqual(runner.statuses['node_1'], 'completed')
        self.assertIn('rows', runner.outputs['node_1'])

        # Enforce UPDATE disallowed (security constraint violation)
        sql_blocked = "UPDATE users SET role = 'admin'"
        runner.nodes['node_2'] = {"id": "node_2", "type": "SQLNode", "title": "Blocked Update", "config_json": json.dumps({"query": sql_blocked}), "workflow_id": wf_id}
        runner.statuses['node_2'] = 'running'
        runner.run_node('node_2')
        self.assertEqual(runner.statuses['node_2'], 'failed')

    def test_event_bus_and_evaluator_observability(self):
        """6. Verify event contracts published to EventBus, traces and evaluations logged in DB."""
        event_payload = None

        # Setup subscriber
        def test_subscriber(event):
            nonlocal event_payload
            event_payload = event.payload

        event_bus.subscribe("NodeCompleted", test_subscriber)

        # Simulate execution completion event
        now = time.time()
        event_bus.publish("NodeCompleted", {
            "run_id": 999,
            "node_id": "test_node_3",
            "status": "completed",
            "duration_ms": 150,
            "tokens": 420,
            "cost": 0.00084,
            "outputs": "Hello enterprise evaluator"
        })

        # Wait for callback execution
        self.assertIsNotNone(event_payload)
        self.assertEqual(event_payload["node_id"], "test_node_3")
        self.assertEqual(event_payload["tokens"], 420)

        # Check observability traces logger hook writes to database
        # Trigger the listener that logs execution outputs to traces table
        from services.observability_service import ObservabilityService
        
        # Setup a mock workflow run first
        self.cursor.execute("INSERT INTO workflows (title, user_id) VALUES ('Obs Workflow', %s)", (self.test_user_id,))
        wf_id = self.cursor.lastrowid
        self.cursor.execute("INSERT INTO workflow_runs (workflow_id, user_id, status, inputs) VALUES (%s, %s, 'queued', '{}')", (wf_id, self.test_user_id))
        run_id = self.cursor.lastrowid
        self.conn.commit()

        # Log trace (passing parent_node_id=None, trace_logs="Trace logs", latency_ms=150)
        ObservabilityService.log_trace(run_id, "test_node_3", None, "completed", "Input prompt", "Output summary", "Trace logs", 150)
        
        # Verify db insert
        self.cursor.execute("SELECT * FROM observability_traces WHERE run_id = %s", (run_id,))
        trace = self.cursor.fetchone()
        self.assertIsNotNone(trace)
        self.assertEqual(trace["node_id"], "test_node_3")
        self.assertEqual(trace["latency_ms"], 150)

    def test_state_machine_transitions(self):
        """7. Verify run loop transition conditions prevent invalid execution state updates."""
        # Create a mock run
        self.cursor.execute("INSERT INTO workflows (title, user_id) VALUES ('SM Workflow', %s)", (self.test_user_id,))
        wf_id = self.cursor.lastrowid
        self.cursor.execute("INSERT INTO workflow_runs (workflow_id, user_id, status, inputs) VALUES (%s, %s, 'queued', '{}')", (wf_id, self.test_user_id))
        run_id = self.cursor.lastrowid
        self.conn.commit()

        # Validate allowed transitions
        self.assertTrue(app.transition_run_status(run_id, "running"))
        self.assertTrue(app.transition_run_status(run_id, "paused"))
        self.assertTrue(app.transition_run_status(run_id, "resumed"))
        self.assertTrue(app.transition_run_status(run_id, "running"))
        self.assertTrue(app.transition_run_status(run_id, "completed"))

        # Block invalid transition: direct jump from completed to running
        self.assertFalse(app.transition_run_status(run_id, "running"))

    def test_custom_plugin_registration(self):
        """8. Verify Custom plugin load, metadata retrieval, and Execution context resolution."""
        # Ensure JiraPlugin is registered
        PluginSDK.load_plugins_from_dir("plugins")
        plugin_class = PluginSDK.get_plugin("JiraPlugin")
        self.assertIsNotNone(plugin_class)
        
        # Verify stable plugin metadata version declarations
        self.assertEqual(getattr(plugin_class, "api_version", ""), "v1")
        self.assertEqual(getattr(plugin_class, "plugin_version", ""), "1.0.0")

        # Run execute context
        ctx = NodeExecutionContext(
            run_id=101,
            workflow_id=202,
            variables={"summary": "Enterprise Bug Ticket"},
            memory={},
            artifacts=[]
        )
        plugin_inst = plugin_class(config={"action": "create_ticket"})
        res = plugin_inst.execute(ctx)
        
        self.assertTrue(res["success"])
        self.assertEqual(res["ticket_key"], "PROJ-101")

    def test_streaming_service(self):
        """9. Verify Server-Sent Event streaming token response yields correctly."""
        formatted = StreamingService.format_sse_event("token", "token1 ")
        expected_json = {"event": "token", "data": "token1 "}
        
        # Verify that it formats to standard SSE spec correctly
        self.assertTrue(formatted.startswith("data: "))
        self.assertTrue(formatted.endswith("\n\n"))
        parsed = json.loads(formatted[6:-2])
        self.assertEqual(parsed, expected_json)

if __name__ == "__main__":
    unittest.main()
