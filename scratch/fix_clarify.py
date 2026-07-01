"""
Rewrites api_clarify_prompt to use OpenRouter as middle fallback and removes GROQ_EXHAUSTED global state.
Also adds OpenRouter MCQ generation to LLMService.
"""
import re
import sys

app_path = 'D:/Nexabuild/forge/app.py'
with open(app_path, 'r', encoding='utf-8') as f:
    content = f.read()

# ---- 1. Replace the api_clarify_prompt body ----
old_clarify = '''    global GROQ_EXHAUSTED
    source = "groq"
    result = None
    detected_category = category if category else "Image gen"
    
    # Intent category detection
    low = raw_prompt.lower()
    if any(k in low for k in ["earn", "money", "income", "sell", "revenue", "business", "profit", "monetize"]):
        detected_category = "Business/Monetization"
    elif not category:
        if any(k in low for k in ["code", "python", "script", "scrap", "developer", "html", "css", "js", "program", "web dev"]):
            detected_category = "Code"
        elif any(k in low for k in ["write", "essay", "brief", "email", "blog", "story", "copy", "writing"]):
            detected_category = "Writing"
        elif any(k in low for k in ["bot", "chat", "persona", "helper", "support", "chatbot"]):
            detected_category = "Chatbot"
            
    if not GROQ_EXHAUSTED:
        try:
            from groq import Groq
            import httpx
            api_key = config.GROQ_API_KEY
            if not api_key:
                raise Exception("No Groq API Key")
            client = Groq(api_key=api_key, http_client=httpx.Client())
            
            system_instructions = (
                "You are ForgePrompt AI, an elite prompt engineering architect.\\n"
                "The user will describe a concept or project they want to create. Analyze their intent very carefully.\\n"
                "Your job is to ask them exactly 3 smart, specific, contextual questions to refine their idea based on their specific domain.\\n"
                "INTENT DETECTION & QUESTION ROUTING RULES:\\n"
                "- If user mentions business/monetization keywords (e.g., earn, money, income, sell, revenue, business, profit):\\n"
                "  → ALWAYS route to BUSINESS/MONETIZATION mode. Ask about: Business Model (e.g. subscriptions, e-commerce, affiliate, ads), Target Audience, and Core Revenue Stream/Service.\\n"
                "  → NEVER ask about visual aesthetics, layouts, or animations for a monetization/business request. Focus strictly on business logic and conversion strategies.\\n"
                "- If user mentions image/visual keywords (e.g., image, photo, art, generate, draw, visual):\\n"
                "  → Route to IMAGE GENERATION mode. Ask about: Art Style, Atmospheric Lighting, Mood/Composition.\\n"
                "- If user mentions web development keywords (e.g., website, dashboard, app, UI, design):\\n"
                "  → Route to WEB DEV mode. Ask about: Purpose & Target Audience first, then Layout/Grid structure, then core features.\\n"
                "- If user mentions coding keywords (e.g., code, script, function, API, backend):\\n"
                "  → Route to CODE mode. Ask about: Language/Framework, Core Functionality/Goal, Architecture/Complexity.\\n"
                "- If user mentions content keywords (e.g., write, blog, post, content, email, caption):\\n"
                "  → Route to CONTENT WRITING mode. Ask about: Format/Structure, Tone/Voice, Platform/Length.\\n\\n"
                "CRITICAL RULES FOR JSON OUTPUT:\\n"
                "1. Do NOT list the choices/options inside the 'question' string itself. Keep the question text clean, focused, and conversational (e.g., 'What is the primary business model for this website?'). Do not write 'Which would you prefer: a, b, or c?'. The front-end renders the options as clickable button pills from the 'options' array.\\n"
                "2. Place the exact choice strings strictly inside the 'options' array (3-4 choices per question).\\n"
                "3. Do NOT include any prefix like 'Nice concept! ⚡' or 'Great choice!' in the question text. Start directly with the question. The UI handles the prefixes automatically.\\n"
                "4. Return ONLY a valid JSON array matching this exact format, with no markdown block, no intros/outros:\\n"
                "[{\\"id\\":1,\\"question\\":\\"Question text here?\\",\\"options\\":[\\"Option 1\\",\\"Option 2\\",\\"Option 3\\",\\"Option 4\\"]}]"
            )
            
            user_query = f"Create targeted questions for this concept: '{raw_prompt}'"
            if category:
                user_query += f"\\nThe user has pre-selected the category/focus: '{category}'."

            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": system_instructions},
                    {"role": "user", "content": user_query}
                ],
                max_tokens=1000,
                temperature=0.2
            )
            raw_output = response.choices[0].message.content.strip()
            cleaned = raw_output.replace("```json", "").replace("```", "").strip()
            result = json.loads(cleaned)
        except Exception as e:
            if "rate_limit" in str(e).lower() or "quota" in str(e).lower() or "limit" in str(e).lower() or not config.GROQ_API_KEY:
                GROQ_EXHAUSTED = False
                print("⚠️ Groq exhausted — switching to Prometheus local fallback")
            else:
                try:
                    result = prometheus_engine.generate_mcqs(raw_prompt)
                    source = "prometheus"
                except Exception as ex:
                    print(f"[Prometheus Fallback MCQ Error] {str(ex)}")

    if GROQ_EXHAUSTED or result is None:
        try:
            result = prometheus_engine.generate_mcqs(raw_prompt)
            source = "prometheus"
        except Exception as e:
            print(f"[Prometheus Fallback MCQ Error] {str(e)}")
            # Safety static questions fallback
            result = [
                {"id": 1, "question": "What is the preferred visual/art style?", "options": ["Cinematic Realism", "Figma mockup UI", "Anime digital art", "Minimal slate"]},
                {"id": 2, "question": "Select the ideal atmospheric lighting", "options": ["Volumetric neon glow", "Bright daylight studio", "Dramatic chiaroscuro", "Minimal moody slate"]}
            ]
            source = "fallback"

    return jsonify({
        "success": True,
        "type_detected": detected_category,
        "questions": result,
        "source": source
    })'''

new_clarify = '''    source = "groq"
    result = None
    detected_category = category if category else "Image gen"
    
    # Intent category detection
    low = raw_prompt.lower()
    if any(k in low for k in ["earn", "money", "income", "sell", "revenue", "business", "profit", "monetize"]):
        detected_category = "Business/Monetization"
    elif not category:
        if any(k in low for k in ["code", "python", "script", "scrap", "developer", "html", "css", "js", "program", "web dev"]):
            detected_category = "Code"
        elif any(k in low for k in ["write", "essay", "brief", "email", "blog", "story", "copy", "writing"]):
            detected_category = "Writing"
        elif any(k in low for k in ["bot", "chat", "persona", "helper", "support", "chatbot"]):
            detected_category = "Chatbot"

    system_instructions = (
        "You are ForgePrompt AI, an elite prompt engineering architect.\\n"
        "The user will describe a concept or project they want to create. Analyze their intent very carefully.\\n"
        "Your job is to ask them exactly 3 smart, specific, contextual questions to refine their idea based on their specific domain.\\n"
        "INTENT DETECTION & QUESTION ROUTING RULES:\\n"
        "- If user mentions business/monetization keywords (e.g., earn, money, income, sell, revenue, business, profit):\\n"
        "  → ALWAYS route to BUSINESS/MONETIZATION mode. Ask about: Business Model (e.g. subscriptions, e-commerce, affiliate, ads), Target Audience, and Core Revenue Stream/Service.\\n"
        "  → NEVER ask about visual aesthetics, layouts, or animations for a monetization/business request. Focus strictly on business logic and conversion strategies.\\n"
        "- If user mentions image/visual keywords (e.g., image, photo, art, generate, draw, visual):\\n"
        "  → Route to IMAGE GENERATION mode. Ask about: Art Style, Atmospheric Lighting, Mood/Composition.\\n"
        "- If user mentions web development keywords (e.g., website, dashboard, app, UI, design):\\n"
        "  → Route to WEB DEV mode. Ask about: Purpose & Target Audience first, then Layout/Grid structure, then core features.\\n"
        "- If user mentions coding keywords (e.g., code, script, function, API, backend):\\n"
        "  → Route to CODE mode. Ask about: Language/Framework, Core Functionality/Goal, Architecture/Complexity.\\n"
        "- If user mentions content keywords (e.g., write, blog, post, content, email, caption):\\n"
        "  → Route to CONTENT WRITING mode. Ask about: Format/Structure, Tone/Voice, Platform/Length.\\n\\n"
        "CRITICAL RULES FOR JSON OUTPUT:\\n"
        "1. Do NOT list the choices/options inside the 'question' string itself. Keep the question text clean, focused, and conversational.\\n"
        "2. Place the exact choice strings strictly inside the 'options' array (3-4 choices per question).\\n"
        "3. Do NOT include any prefix like 'Nice concept! ⚡' or 'Great choice!' in the question text.\\n"
        "4. Return ONLY a valid JSON array matching this exact format, with no markdown block, no intros/outros:\\n"
        "[{\\"id\\":1,\\"question\\":\\"Question text here?\\",\\"options\\":[\\"Option 1\\",\\"Option 2\\",\\"Option 3\\",\\"Option 4\\"]}]"
    )
    
    user_query = f"Create targeted questions for this concept: '{raw_prompt}'"
    if category:
        user_query += f"\\nThe user has pre-selected the category/focus: '{category}'."

    # ---- Tier 1: Primary Groq Key ----
    groq_key = config.GROQ_API_KEY
    if groq_key:
        try:
            from groq import Groq
            import httpx
            client = Groq(api_key=groq_key, http_client=httpx.Client())
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": system_instructions},
                    {"role": "user", "content": user_query}
                ],
                max_tokens=1000,
                temperature=0.2
            )
            raw_output = response.choices[0].message.content.strip()
            cleaned = raw_output.replace("```json", "").replace("```", "").strip()
            result = json.loads(cleaned)
            source = "groq"
            print("[Cascade] MCQ generated via Primary Groq.")
        except Exception as e:
            print(f"[Cascade] Primary Groq MCQ failed: {e}")

    # ---- Tier 2: OpenRouter ----
    if result is None:
        or_key = config.OPEN_ROUTER_API_KEY
        if or_key:
            try:
                import requests as req_lib
                headers = {
                    "Authorization": f"Bearer {or_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://forgeprompt.com",
                    "X-Title": "ForgePrompt"
                }
                payload = {
                    "model": "meta-llama/llama-3.3-70b-instruct",
                    "messages": [
                        {"role": "system", "content": system_instructions},
                        {"role": "user", "content": user_query}
                    ],
                    "max_tokens": 1000,
                    "temperature": 0.2
                }
                res = req_lib.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=45)
                if res.status_code == 200:
                    raw_output = res.json()["choices"][0]["message"]["content"].strip()
                    cleaned = raw_output.replace("```json", "").replace("```", "").strip()
                    result = json.loads(cleaned)
                    source = "openrouter"
                    print("[Cascade] MCQ generated via OpenRouter.")
                else:
                    print(f"[Cascade] OpenRouter MCQ failed: {res.status_code} {res.text[:200]}")
            except Exception as e:
                print(f"[Cascade] OpenRouter MCQ exception: {e}")

    # ---- Tier 3: Local Prometheus ----
    if result is None:
        try:
            result = prometheus_engine.generate_mcqs(raw_prompt)
            source = "prometheus"
            print("[Cascade] MCQ generated via local Prometheus.")
        except Exception as e:
            print(f"[Prometheus Fallback MCQ Error] {str(e)}")
            # Safety static questions fallback
            result = [
                {"id": 1, "question": "What is the preferred visual/art style?", "options": ["Cinematic Realism", "Figma mockup UI", "Anime digital art", "Minimal slate"]},
                {"id": 2, "question": "Select the ideal atmospheric lighting", "options": ["Volumetric neon glow", "Bright daylight studio", "Dramatic chiaroscuro", "Minimal moody slate"]}
            ]
            source = "fallback"

    # Validate result
    if isinstance(result, list):
        for q in result:
            if not isinstance(q.get("options"), list) or len(q.get("options", [])) == 0:
                q["options"] = ["Yes", "No", "Not sure"]

    return jsonify({
        "success": True,
        "type_detected": detected_category,
        "questions": result,
        "source": source
    })'''

if old_clarify in content:
    content = content.replace(old_clarify, new_clarify)
    with open(app_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("done - clarify-prompt updated")
else:
    print("ERROR: old_clarify block not found")
