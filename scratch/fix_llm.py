import re
path = 'D:/Nexabuild/forge/services/llm_service.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

target = """                if system_prompt:
                    payload["messages"].append({"role": "system", "content": system_prompt})
                payload["messages"].append({"role": "user", "content": prompt})"""

replacement = """                if system_prompt:
                    payload["messages"].append({"role": "system", "content": system_prompt})
                if chat_history:
                    for msg in chat_history:
                        payload["messages"].append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
                payload["messages"].append({"role": "user", "content": prompt})"""

content = content.replace(target, replacement)
with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("done")
