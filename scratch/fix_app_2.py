import re
path = 'D:/Nexabuild/forge/app.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

start_idx = content.find('def api_forge_prompt():')
end_idx = content.find('@app.route("/api/analyze-vision"', start_idx)

if start_idx != -1 and end_idx != -1:
    func_content = content[start_idx:end_idx]
    
    # We want to replace the whole body of api_forge_prompt
    replacement = """def api_forge_prompt():
    raw_payload = request.json
    input_text = raw_payload.get("prompt", "").strip()
    type_detected = raw_payload.get("category", "")
    mcq_answers = raw_payload.get("mcq_answers", {})
    chat_history = raw_payload.get("chat_history", [])
    user_id = raw_payload.get("user_id", "guest")
    template_name = raw_payload.get("template_name", None)

    if not input_text:
        return jsonify({"success": False, "error": "No input prompt provided."}), 400

    if template_name:
        log_analytics_event("template_used", user_id=user_id, template_name=template_name)

    from services.llm_service import LLMService
    
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
            if chat_history:
                yield "\\n\\nAnything else to adjust?"
        except Exception as e:
            app.logger.error(f"Generation failed: {str(e)}", exc_info=True)
            yield "\\n[Error] Failed to generate prompt."
            
    return Response(generate_prompt_stream(), mimetype="text/plain")

"""
    
    new_content = content[:start_idx] + replacement + content[end_idx:]
    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("done")
else:
    print("could not find boundaries")
