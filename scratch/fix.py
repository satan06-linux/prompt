import re
path = 'D:/Nexabuild/forge/templates/index.html'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

target = """            });
        }

            const bubble = document.createElement("div");
            bubble.className = "chat-bubble";"""

replacement = """            });
        }

        function handleInputKeydown(event) {
            if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                submitUserConcept();
            }
        }

        function selectCategory(category, buttonEl, preventReset = false) {
            detectedType = category;
            const siblings = document.querySelectorAll(".chip-btn");
            siblings.forEach(s => s.classList.remove("active"));
            buttonEl.classList.add("active");
            
            // If there's an active session, reset silently to start fresh
            if (!preventReset && (lastForgedPromptText || conversationHistory.length > 0)) {
                resetChatSession(true);
            }
        }

        // --- CHAT APPEND UTILITIES ---

        function appendUserBubble(text) {
            const container = document.getElementById("chat-messages");
            
            const row = document.createElement("div");
            row.className = "message-row user-row";

            const bubble = document.createElement("div");
            bubble.className = "chat-bubble";"""

content = content.replace(target, replacement)
with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("done")
