import sys
import os
import json
import jwt
from datetime import datetime, timedelta

# Force UTF-8 mode
sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None

sys.path.append("d:/Nexabuild/forge")
import app
import config
import models

def print_result(name, passed):
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] {name}")
    return passed

def run_phase2_tests():
    print("=" * 60)
    print("      🚀 FORGE.AI PHASE 2 INTEGRATION & VERIFICATION")
    print("=" * 60)

    app.app.config["TESTING"] = True
    client = app.app.test_client()
    
    all_passed = True
    secret = config.SECRET_KEY
    
    # Generate user tokens
    token_user_8888 = jwt.encode({
        "user_id": 8888,
        "name": "User 8888",
        "email": "user8888@example.com",
        "role": "user",
        "exp": datetime.utcnow() + timedelta(hours=1)
    }, secret, algorithm="HS256")

    token_admin_9999 = jwt.encode({
        "user_id": 9999,
        "name": "Admin 9999",
        "email": "admin9999@example.com",
        "role": "admin",
        "exp": datetime.utcnow() + timedelta(hours=1)
    }, secret, algorithm="HS256")

    # 1. Clean up and set up test data in the database
    conn = None
    cursor = None
    try:
        conn = models.get_db_connection()
        cursor = conn.cursor()
        
        # Clean up database test records
        cursor.execute("DELETE FROM feedback WHERE user_id IN (8888, 9999)")
        cursor.execute("DELETE FROM prompts WHERE user_id IN (8888, 9999)")
        cursor.execute("DELETE FROM analytics_events WHERE user_id IN (8888, 9999)")
        cursor.execute("DELETE FROM users WHERE id IN (8888, 9999)")
        
        # Insert test users
        cursor.execute(
            "INSERT INTO users (id, name, email, password_hash, role) VALUES (%s, %s, %s, %s, %s)",
            (8888, "User 8888", "user8888@example.com", "dummy_hash", "user")
        )
        cursor.execute(
            "INSERT INTO users (id, name, email, password_hash, role) VALUES (%s, %s, %s, %s, %s)",
            (9999, "Admin 9999", "admin9999@example.com", "dummy_hash", "admin")
        )
        
        # Insert prompts for user 8888
        # Prompt 1: Python Scraper
        cursor.execute(
            "INSERT INTO prompts (id, user_id, input_text, category, mcq_questions, mcq_answers, generated_prompt) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (1001, 8888, "Python scraper script", "Code Gen", "[]", "{}", "Master Python scraper prompt.")
        )
        # Prompt 2: React UI
        cursor.execute(
            "INSERT INTO prompts (id, user_id, input_text, category, mcq_questions, mcq_answers, generated_prompt) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (1002, 8888, "React UI component", "App UI", "[]", "{}", "React visual cards design prompt.")
        )
        # Prompt 3: Python Learn
        cursor.execute(
            "INSERT INTO prompts (id, user_id, input_text, category, mcq_questions, mcq_answers, generated_prompt) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (1003, 8888, "Learn Python logic", "Research", "[]", "{}", "Learn Python course study outline.")
        )
        
        # Insert prompt for user 9999 (Secret Admin Prompt)
        cursor.execute(
            "INSERT INTO prompts (id, user_id, input_text, category, mcq_questions, mcq_answers, generated_prompt) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (1099, 9999, "Secret admin configuration", "Code Gen", "[]", "{}", "Highly private database credential config prompt.")
        )
        
        conn.commit()
        print("✅ Test environment and mockup records initialized in MySQL database.")
    except Exception as e:
        print(f"❌ Database initialization failed: {str(e)}")
        return False
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    # --- Test 2D: Starter Prompt Templates ---
    print("\n--- Test 2D: Predefined Starter Templates ---")
    res = client.get("/api/templates")
    templates_valid = False
    if res.status_code == 200:
        data = json.loads(res.data)
        if data.get("success") and len(data.get("templates", [])) > 0:
            templates_valid = True
            print(f"Fetched {len(data['templates'])} templates.")
            for t in data["templates"]:
                print(f"  - [{t['category']}] {t['name']}: '{t['description']}'")
    all_passed &= print_result("A. Fetch Starter Templates (/api/templates)", templates_valid)

    # --- Test 2C: Saved Prompts Favorites toggles ---
    print("\n--- Test 2C: Favorites Toggle Endpoint ---")
    # Call toggle endpoint (Expect is_favorite to become True)
    res_toggle_1 = client.post("/api/history/favorite", 
                              headers={"Authorization": f"Bearer {token_user_8888}"},
                              json={"prompt_id": 1001})
    passed_toggle_1 = False
    if res_toggle_1.status_code == 200:
        data = json.loads(res_toggle_1.data)
        passed_toggle_1 = data.get("success") == True and data.get("is_favorite") == True
    all_passed &= print_result("B. Toggle Favorite 1001 ON (Expects True)", passed_toggle_1)

    # Call toggle endpoint again (Expect is_favorite to become False)
    res_toggle_2 = client.post("/api/history/favorite", 
                              headers={"Authorization": f"Bearer {token_user_8888}"},
                              json={"prompt_id": 1001})
    passed_toggle_2 = False
    if res_toggle_2.status_code == 200:
        data = json.loads(res_toggle_2.data)
        passed_toggle_2 = data.get("success") == True and data.get("is_favorite") == False
    all_passed &= print_result("C. Toggle Favorite 1001 OFF (Expects False)", passed_toggle_2)

    # Verify analytics_events table logs 'favorite_toggled' event type with correct metadata state
    passed_favorite_logs = False
    try:
        conn = models.get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM analytics_events WHERE user_id = 8888 AND event_type = 'favorite_toggled' ORDER BY created_at ASC")
        logs = cursor.fetchall()
        if len(logs) == 2:
            meta_1 = json.loads(logs[0]["event_metadata"]) if isinstance(logs[0]["event_metadata"], str) else logs[0]["event_metadata"]
            meta_2 = json.loads(logs[1]["event_metadata"]) if isinstance(logs[1]["event_metadata"], str) else logs[1]["event_metadata"]
            if meta_1.get("new_state") == True and meta_2.get("new_state") == False:
                passed_favorite_logs = True
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"❌ Failed to verify favorite telemetry log in database: {e}")
    all_passed &= print_result("D. Verify 'favorite_toggled' Telemetry Metadata Logs", passed_favorite_logs)

    # --- Test 2C: Saved Prompts Search ---
    print("\n--- Test 2C: Searchable History Logs ---")
    
    # Case A: Retrieve all history (expects 3)
    res_history_all = client.get("/api/history", headers={"Authorization": f"Bearer {token_user_8888}"})
    passed_history_all = False
    if res_history_all.status_code == 200:
        data = json.loads(res_history_all.data)
        passed_history_all = data.get("success") == True and len(data.get("history", [])) == 3
    all_passed &= print_result("E. Get Unfiltered History (Expects 3 prompts)", passed_history_all)

    # Case B: Search "python" (expects 2 matching prompts: 1001 and 1003)
    res_search_python = client.get("/api/history?search=python", headers={"Authorization": f"Bearer {token_user_8888}"})
    passed_search_python = False
    if res_search_python.status_code == 200:
        data = json.loads(res_search_python.data)
        history = data.get("history", [])
        if len(history) == 2 and any(p["id"] == 1001 for p in history) and any(p["id"] == 1003 for p in history):
            passed_search_python = True
    all_passed &= print_result("F. Search History for 'python' (Expects 2 prompts)", passed_search_python)

    # Case C: Search "react" (expects 1 matching prompt: 1002)
    res_search_react = client.get("/api/history?search=react", headers={"Authorization": f"Bearer {token_user_8888}"})
    passed_search_react = False
    if res_search_react.status_code == 200:
        data = json.loads(res_search_react.data)
        history = data.get("history", [])
        if len(history) == 1 and history[0]["id"] == 1002:
            passed_search_react = True
    all_passed &= print_result("G. Search History for 'react' (Expects 1 prompt)", passed_search_react)

    # --- SQL Injection Test on History Search ---
    print("\n--- Security Verification: SQL Injection Search Test ---")
    # Attacking query: ?search=' OR 1=1 --
    # Expected: Parameterized SQL prevents injection. Returns ONLY user 8888's prompts (none matching the literal pattern),
    # and absolutely does NOT return user 9999's private prompts.
    res_attack = client.get("/api/history?search='+OR+1%3D1+--", headers={"Authorization": f"Bearer {token_user_8888}"})
    passed_sql_injection = False
    if res_attack.status_code == 200:
        data = json.loads(res_attack.data)
        history = data.get("history", [])
        
        # Verify that we received 0 prompts (since no prompt has input_text containing "' OR 1=1 --")
        # and specifically, make sure admin prompt 1099 is NOT in the list!
        contains_admin_leak = any(p["id"] == 1099 for p in history)
        if len(history) == 0 and not contains_admin_leak:
            passed_sql_injection = True
        else:
            print(f"⚠️ SQL Injection vulnerability detected! Returned count: {len(history)} (leak admin: {contains_admin_leak})")
    all_passed &= print_result("H. SQL Injection attack '?search=\' OR 1=1 --' (Expects 0 prompts, NO Admin leak)", passed_sql_injection)

    # --- Test 2F: User Feedback Collection ---
    print("\n--- Test 2F: Feedback Loops ---")
    
    # Submit rating feedback
    res_feedback_rating = client.post("/api/feedback",
                                     headers={"Authorization": f"Bearer {token_user_8888}"},
                                     json={"feedback_type": "rating", "rating": 5, "comment": "Prompt rated 5/5 stars.", "prompt_id": 1001})
    passed_feedback_rating = res_feedback_rating.status_code == 200 and json.loads(res_feedback_rating.data).get("success") == True
    all_passed &= print_result("I. Submit 5-star Rating Feedback (/api/feedback)", passed_feedback_rating)

    # Submit issue feedback
    res_feedback_issue = client.post("/api/feedback",
                                    headers={"Authorization": f"Bearer {token_user_8888}"},
                                    json={"feedback_type": "issue", "comment": "The alternative variations failed to load."})
    passed_feedback_issue = res_feedback_issue.status_code == 200 and json.loads(res_feedback_issue.data).get("success") == True
    all_passed &= print_result("J. Submit Bug Issue Feedback (/api/feedback)", passed_feedback_issue)

    # --- Test 2E: Telemetry Analytics stats ---
    print("\n--- Test 2E: Admin Console Metrics & Analytics ---")
    
    # Request stats dashboard using Admin token
    res_stats = client.get("/api/admin/stats", headers={"Authorization": f"Bearer {token_admin_9999}"})
    passed_stats = False
    if res_stats.status_code == 200:
        data = json.loads(res_stats.data)
        analytics = data.get("analytics", {})
        feedback = data.get("feedback", [])
        
        # Verify telemetry keys exist
        if "total_visitors" in analytics and "dau" in analytics and "returning_users" in analytics and "categories" in analytics and "templates" in analytics:
            # Verify feedback items returned (at least the two we submitted)
            if len(feedback) >= 2:
                passed_stats = True
                print(f"  - Total Visitors: {analytics['total_visitors']}")
                print(f"  - Daily Active Users: {analytics['dau']}")
                print(f"  - Returning Users: {analytics['returning_users']}")
                print(f"  - Feedback Records Count: {len(feedback)}")
    all_passed &= print_result("K. Fetch Admin Stats Dashboard (Expects full telemetry and feedback logs)", passed_stats)

    # Clean up test database records
    try:
        conn = models.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM feedback WHERE user_id IN (8888, 9999)")
        cursor.execute("DELETE FROM prompts WHERE user_id IN (8888, 9999)")
        cursor.execute("DELETE FROM analytics_events WHERE user_id IN (8888, 9999)")
        cursor.execute("DELETE FROM users WHERE id IN (8888, 9999)")
        conn.commit()
        cursor.close()
        conn.close()
        print("🧹 Cleaned up temporary test database records.")
    except Exception as e:
        print(f"🧹 Database cleanup failed: {e}")

    print("=" * 60)
    if all_passed:
        print("🎉 ALL PHASE 2 EXIT CRITERIA VALIDATED AND PASSED SUCCESSFULLY!")
    else:
        print("❌ INTEGRATION TESTS ENCOUNTERED FAILURES.")
    print("=" * 60)
    return all_passed

if __name__ == "__main__":
    success = run_phase2_tests()
    sys.exit(0 if success else 1)
