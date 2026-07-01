import re
path = 'D:/Nexabuild/forge/app.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

target = """    global GROQ_EXHAUSTED
    source_model = "groq"
    
    # Construct the instruction specifications
    system_prompt = (
        "You are ForgePrompt AI, an elite prompt engineering architect.\\n"
        "The user will describe a concept or project they want to create, along with their answers to clarifying questions.\\n"
        "Your job is to generate a comprehensive, highly-structured, production-ready engineering prompt based EXACTLY on their requirements.\\n\\n"
        "CRITICAL RULES:\\n"
        "1. DO NOT INVENT FRAMEWORKS. If the user did not specify a tech stack (e.g. React, Next.js, Node, Postgres), default to generic, un-opinionated terms (e.g. 'Frontend Framework', 'Relational Database').\\n"
        "2. If they did specify frameworks in their choices, you MUST strictly adhere to them.\\n"
        "3. Output ONLY the markdown prompt. No intros, no conversational text, no wrappers like ```markdown.\\n"
        "4. Your output MUST follow this exact structure:\\n\\n"
        "# Project Goal\\n[Short description]\\n\\n"
        "# Project Type\\n[e.g., Web App, Mobile App, Script]\\n\\n"
        "# Functional Requirements\\n- [Req 1]\\n- [Req 2]\\n\\n"
        "# Core Features\\n- [Feature 1]\\n- [Feature 2]\\n\\n"
        "# Tech Stack\\n- Frontend: [Framework]\\n- Backend: [Framework]\\n- DB: [Database]\\n\\n"
        "# Constraints\\n- [Constraint 1]\\n\\n"
        "# Optional Enhancements\\n- [Enhancement 1]"
    )

    selections_str = "\\n".join([f"- {k}: {v}" for k, v in mcq_answers.items()])
    
    user_query = (
        f"Goal/Vision: {input_text}\\n"
        f"Domain Type: {type_detected}\\n\\n"
        f"Tailored user choices:\\n{selections_str}"
    )

    if not GROQ_EXHAUSTED:
        try:
            from groq import Groq
            import httpx
            api_key = config.GROQ_API_KEY
            if not api_key:
                raise Exception("No Groq API key")
            client = Groq(api_key=api_key, http_client=httpx.Client())
            
            messages_payload = []
            messages_payload.append({"role": "system", "content": system_prompt})
            
            if chat_history:
                for msg in chat_history:
                    messages_payload.append({
                        "role": msg.get("role", "user"),
                        "content": msg.get("content", "")
                    })
            else:
                messages_payload.append({"role": "user", "content": user_query})

            def groq_streaming_generator():
                try:
                    response = client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=messages_payload,
                        max_tokens=3000,
                        temperature=0.3,
                        stream=True
                    )
                    for chunk in response:
                        chunk_text = chunk.choices[0].delta.content
                        if chunk_text:
                            yield chunk_text
                except Exception as e:
                    app.logger.error(f"Streaming prompt error: {str(e)}", exc_info=True)
                    yield "\\n[Streaming Error] Failed to retrieve prompt stream."
            
            return Response(groq_streaming_generator(), mimetype="text/plain")
        except Exception as e:
            if "rate_limit" in str(e).lower() or "quota" in str(e).lower() or "limit" in str(e).lower():
                GROQ_EXHAUSTED = False
                app.logger.warning("Groq rate limit exceeded — switching to Prometheus local fallback")

    # Local Prometheus fallback (no streaming for local model for stability)
    def prometheus_static_generator():
        try:
            result = prometheus_engine.generate_prompt(input_text, type_detected, mcq_answers)
            # Append refinement guide if in refinement mode
            if chat_history:
                result += "\\n\\nAnything else to adjust?"
            yield result
        except Exception as e:
            app.logger.error(f"Local fallback generation failed: {str(e)}", exc_info=True)
            yield "\\n[Local Fallback Error] Failed to generate prompt."

    return Response(prometheus_static_generator(), mimetype="text/plain")"""

replacement = """    from services.llm_service import LLMService
    
    # Construct the instruction specifications
    system_prompt = (
        "You are ForgePrompt AI, an elite prompt engineering architect.\\n"
        "The user will describe a concept or project they want to create, along with their answers to clarifying questions.\\n"
        "Your job is to generate a comprehensive, highly-structured, production-ready engineering prompt based EXACTLY on their requirements.\\n\\n"
        "CRITICAL RULES:\\n"
        "1. DO NOT INVENT FRAMEWORKS. If the user did not specify a tech stack (e.g. React, Next.js, Node, Postgres), default to generic, un-opinionated terms (e.g. 'Frontend Framework', 'Relational Database').\\n"
        "2. If they did specify frameworks in their choices, you MUST strictly adhere to them.\\n"
        "3. Output ONLY the markdown prompt. No intros, no conversational text, no wrappers like ```markdown.\\n"
        "4. Your output MUST follow this exact structure:\\n\\n"
        "# Project Goal\\n[Short description]\\n\\n"
        "# Project Type\\n[e.g., Web App, Mobile App, Script]\\n\\n"
        "# Functional Requirements\\n- [Req 1]\\n- [Req 2]\\n\\n"
        "# Core Features\\n- [Feature 1]\\n- [Feature 2]\\n\\n"
        "# Tech Stack\\n- Frontend: [Framework]\\n- Backend: [Framework]\\n- DB: [Database]\\n\\n"
        "# Constraints\\n- [Constraint 1]\\n\\n"
        "# Optional Enhancements\\n- [Enhancement 1]"
    )

    selections_str = "\\n".join([f"- {k}: {v}" for k, v in mcq_answers.items()])
    
    user_query = (
        f"Goal/Vision: {input_text}\\n"
        f"Domain Type: {type_detected}\\n\\n"
        f"Tailored user choices:\\n{selections_str}"
    )

    def generate_prompt_stream():
        try:
            for chunk in LLMService.call_stream("groq", "llama-3.3-70b-versatile", user_query, system_prompt, max_tokens=3000, chat_history=chat_history):
                yield chunk
            if chat_history and "Anything else to adjust?" not in chunk:
                yield "\\n\\nAnything else to adjust?"
        except Exception as e:
            app.logger.error(f"Generation failed: {str(e)}", exc_info=True)
            yield "\\n[Error] Failed to generate prompt."
            
    return Response(generate_prompt_stream(), mimetype="text/plain")"""

if target in content:
    content = content.replace(target, replacement)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("done")
else:
    print("target not found")
