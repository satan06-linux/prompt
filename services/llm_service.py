import os
import requests
import json
import logging
import time
import config

logger = logging.getLogger(__name__)

# Persistent connection pool session to optimize performance and prevent handshake overhead
_session = requests.Session()

# Cached local model objects to prevent reload latency spikes
_local_model = None
_local_tokenizer = None

class LLMService:
    @staticmethod
    def get_provider_client(provider_name, custom_key=None, custom_endpoint=None):
        """Preserved for signature backward-compatibility across features."""
        return None

    @staticmethod
    def call(provider_name, model_name, prompt, system_prompt=None, max_tokens=1000, temperature=0.7, custom_key=None, custom_endpoint=None, chat_history=None):
        if config.DEC_TOKEN_USAGE:
            compression_rule = "\n\n[CRITICAL OPTIMIZATION ALIVE]: You MUST drastically decrease token usage. Write highly compressed, token-efficient outputs. Use aggressive markdown shorthand. Maximize semantic density. Do NOT output conversational filler."
            system_prompt = (system_prompt or "") + compression_rule

        def build_messages(system, history, user):
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            if history:
                for msg in history:
                    messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
            messages.append({"role": "user", "content": user})
            return messages

        # Step 1. Try Primary Groq key
        groq_key = custom_key or os.getenv("GROQ_API_KEY", "")
        if groq_key:
            try:
                logger.info(f"LLMService: Attempting Primary Groq ({model_name})...")
                headers = {
                    "Authorization": f"Bearer {groq_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": model_name,
                    "messages": build_messages(system_prompt, chat_history, prompt),
                    "max_tokens": max_tokens,
                    "temperature": temperature
                }

                res = _session.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=30)
                if res.status_code == 200:
                    res_json = res.json()
                    text = res_json["choices"][0]["message"]["content"]
                    usage = res_json.get("usage", {})
                    prompt_tokens = usage.get("prompt_tokens", len(prompt) // 4)
                    completion_tokens = usage.get("completion_tokens", len(text) // 4)
                    total_tokens = prompt_tokens + completion_tokens
                    cost = (prompt_tokens * 0.5 + completion_tokens * 1.5) / 1000000.0
                    return {"text": text, "tokens": total_tokens, "cost": cost, "source": "groq"}
                else:
                    logger.warning(f"Primary Groq returned status {res.status_code}: {res.text}")
            except Exception as e:
                logger.warning(f"Primary Groq execution failed: {e}")

        # Step 2. Try OpenRouter key
        or_key = os.getenv("OPEN_ROUTER_API_KEY", "")
        if or_key:
            try:
                logger.info("LLMService: Attempting OpenRouter Fallback...")
                headers = {
                    "Authorization": f"Bearer {or_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://forgeprompt.com",
                    "X-Title": "ForgePrompt"
                }
                # Map models to OpenRouter equivalents from config
                or_model = config.LLM_MODEL_MAPPING.get(model_name.lower(), "meta-llama/llama-3-8b-instruct")
                
                payload = {
                    "model": or_model,
                    "messages": build_messages(system_prompt, chat_history, prompt),
                    "max_tokens": max_tokens,
                    "temperature": temperature
                }

                res = _session.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=45)
                if res.status_code == 200:
                    res_json = res.json()
                    text = res_json["choices"][0]["message"]["content"]
                    usage = res_json.get("usage", {})
                    prompt_tokens = usage.get("prompt_tokens", len(prompt) // 4)
                    completion_tokens = usage.get("completion_tokens", len(text) // 4)
                    total_tokens = prompt_tokens + completion_tokens
                    cost = 0.0
                    return {"text": text, "tokens": total_tokens, "cost": cost, "source": "openrouter"}
                else:
                    logger.warning(f"OpenRouter returned status {res.status_code}: {res.text}")
            except Exception as e:
                logger.warning(f"OpenRouter execution failed: {e}")

        # Step 3. Try Local Prometheus AI fine-tuned model
        try:
            logger.info("LLMService: All cloud endpoints failed or exhausted. Booting local Prometheus AI model...")
            local_prompt = LLMService._call_local_prometheus(prompt, system_prompt, max_tokens, temperature)
            
            # Step 4. Run external critique refinement pass (Secondary Groq key → OpenRouter → bypass)
            logger.info("LLMService: Local prompt generated. Initiating dynamic critique/refinement pass...")
            refined_text, tokens, cost = LLMService._refine_prompt(local_prompt, prompt, system_prompt)
            return {"text": refined_text, "tokens": tokens, "cost": cost, "source": "prometheus"}
        except Exception as e:
            logger.error(f"Local Prometheus AI fallback pipeline crashed: {e}")
            raise Exception(f"Cascade execution failed across all tiers: {str(e)}")

    @staticmethod
    def _call_local_prometheus(prompt, system_prompt=None, max_tokens=1000, temperature=0.7):
        global _local_model, _local_tokenizer
        import torch
        from unsloth import FastLanguageModel
        
        try:
            # Lazy load the 4-bit model to save RAM when not actively prompting
            if _local_model is None:
                logger.info("Lazy loading OMNICORE weights into VRAM...")
                model_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "OMNICORE", "training", "model_weights")
                
                if not os.path.exists(model_dir):
                    raise Exception(f"OMNICORE weights not found at {model_dir}. Please run the training script first.")
                
                # Setup specific Windows allocations
                os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
                
                _local_model, _local_tokenizer = FastLanguageModel.from_pretrained(
                    model_name="unsloth/Qwen2.5-3B-Instruct", 
                    max_seq_length=1024,
                    dtype=torch.float16,
                    load_in_4bit=True,
                    device_map="cuda",
                )
                logger.info("Applying LoRA adapter...")
                _local_model.load_adapter(model_dir)
                FastLanguageModel.for_inference(_local_model)
                logger.info("OMNICORE loaded successfully.")

            # Format the prompt correctly for the model
            formatted_prompt = prompt
            if system_prompt:
                formatted_prompt = f"<|system|>\n{system_prompt}\n<|end|>\n<|user|>\n{prompt}\n<|end|>\n<|assistant|>\n"

            inputs = _local_tokenizer([formatted_prompt], return_tensors="pt").to("cuda")
            outputs = _local_model.generate(**inputs, max_new_tokens=max_tokens, use_cache=True, temperature=temperature)
            
            input_len = inputs["input_ids"].shape[1]
            return _local_tokenizer.decode(outputs[0][input_len:], skip_special_tokens=True).strip()
            
        except Exception as e:
            logger.error(f"Failed to execute local OMNICORE inference: {e}")
            raise Exception(f"Failed to execute local OMNICORE inference: {e}")

    @staticmethod
    def _refine_prompt(generated_prompt, original_prompt, system_prompt=None):
        refine_system_prompt = """You are an expert prompt optimization engine.
Review the candidate prompt generated by a local AI model based on the user's requirements.
Expand it, fill in any missing details (such as folder structures, api designs, coding standards, performance rules, or security constraints), correct any structural or formatting errors, and return a clean, fully-featured, finalized markdown prompt.
Ensure you preserve all user requirements and MCQ constraints.
Output ONLY the final polished prompt in markdown, no explanations, no wrappers.
"""
        refine_user_prompt = f"Original Request/Context:\n{original_prompt}\n\nCandidate Draft Prompt:\n{generated_prompt}"
                
        # 1. Try OpenRouter Key
        or_key = os.getenv("OPEN_ROUTER_API_KEY", "")
        if or_key:
            try:
                logger.info("Refiner Cascade: Attempting OpenRouter...")
                headers = {
                    "Authorization": f"Bearer {or_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://forgeprompt.com",
                    "X-Title": "ForgePrompt"
                }
                payload = {
                    "model": "google/gemini-2.5-flash",
                    "messages": [
                        {"role": "system", "content": refine_system_prompt},
                        {"role": "user", "content": refine_user_prompt}
                    ],
                    "max_tokens": 1200,
                    "temperature": 0.3
                }
                res = _session.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=45)
                if res.status_code == 200:
                    text = res.json()["choices"][0]["message"]["content"].strip()
                    tokens = res.json().get("usage", {}).get("total_tokens", len(text)//4)
                    logger.info("Refiner Cascade: OpenRouter refinement successful.")
                    return text, tokens, 0.0
                else:
                    logger.warning(f"Refiner OpenRouter returned status {res.status_code}: {res.text}")
            except Exception as e:
                logger.warning(f"Refiner Cascade: OpenRouter failed: {e}")
                
        # 3. Bypass: Return Raw local generated prompt
        logger.info("Refiner Cascade: All external APIs failed. Bypassing refinement and returning raw local prompt.")
        return generated_prompt, len(generated_prompt)//4, 0.0

    @staticmethod
    def call_stream(provider_name, model_name, prompt, system_prompt=None, max_tokens=1000, temperature=0.7, custom_key=None, custom_endpoint=None, chat_history=None):
        """
        Streaming cascade: Primary Groq (SSE stream) → OpenRouter (SSE stream) → Prometheus local + Refinement (non-stream).
        Yields text chunks.
        """
        if config.DEC_TOKEN_USAGE:
            compression_rule = "\n\n[CRITICAL OPTIMIZATION ALIVE]: You MUST drastically decrease token usage. Write highly compressed, token-efficient outputs. Use aggressive markdown shorthand. Maximize semantic density. Do NOT output conversational filler."
            system_prompt = (system_prompt or "") + compression_rule

        def build_messages(system, history, user):
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            if history:
                for msg in history:
                    messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
            messages.append({"role": "user", "content": user})
            return messages

        # ---- Tier 1: Primary Groq streaming ----
        groq_key = custom_key or os.getenv("GROQ_API_KEY", "")
        if groq_key:
            try:
                logger.info(f"LLMService Stream: Attempting Primary Groq ({model_name})...")
                headers = {
                    "Authorization": f"Bearer {groq_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": model_name,
                    "messages": build_messages(system_prompt, chat_history, prompt),
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "stream": True
                }
                res = _session.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers=headers, json=payload, timeout=60, stream=True
                )
                if res.status_code == 200:
                    logger.info("LLMService Stream: Groq stream connected, yielding chunks...")
                    for line in res.iter_lines():
                        if line:
                            line_str = line.decode("utf-8") if isinstance(line, bytes) else line
                            if line_str.startswith("data: "):
                                data_str = line_str[6:].strip()
                                if data_str == "[DONE]":
                                    break
                                try:
                                    data = json.loads(data_str)
                                    delta = data["choices"][0].get("delta", {})
                                    chunk_text = delta.get("content", "")
                                    if chunk_text:
                                        yield chunk_text
                                except Exception:
                                    pass
                    return  # Done streaming from Groq
                else:
                    logger.warning(f"LLMService Stream: Primary Groq returned {res.status_code}: {res.text[:200]}")
            except Exception as e:
                logger.warning(f"LLMService Stream: Primary Groq failed: {e}")

        # ---- Tier 2: OpenRouter streaming ----
        or_key = os.getenv("OPEN_ROUTER_API_KEY", "")
        if or_key:
            try:
                logger.info("LLMService Stream: Attempting OpenRouter fallback stream...")
                or_model = config.LLM_MODEL_MAPPING.get(model_name.lower(), "meta-llama/llama-3-8b-instruct")
                headers = {
                    "Authorization": f"Bearer {or_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://forgeprompt.com",
                    "X-Title": "ForgePrompt"
                }
                payload = {
                    "model": or_model,
                    "messages": build_messages(system_prompt, chat_history, prompt),
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "stream": True
                }
                res = _session.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers, json=payload, timeout=60, stream=True
                )
                if res.status_code == 200:
                    logger.info("LLMService Stream: OpenRouter stream connected, yielding chunks...")
                    for line in res.iter_lines():
                        if line:
                            line_str = line.decode("utf-8") if isinstance(line, bytes) else line
                            if line_str.startswith("data: "):
                                data_str = line_str[6:].strip()
                                if data_str == "[DONE]":
                                    break
                                try:
                                    data = json.loads(data_str)
                                    delta = data["choices"][0].get("delta", {})
                                    chunk_text = delta.get("content", "")
                                    if chunk_text:
                                        yield chunk_text
                                except Exception:
                                    pass
                    return  # Done streaming from OpenRouter
                else:
                    logger.warning(f"LLMService Stream: OpenRouter returned {res.status_code}: {res.text[:200]}")
            except Exception as e:
                logger.warning(f"LLMService Stream: OpenRouter failed: {e}")

        # ---- Tier 3: Local Prometheus + Secondary Groq/OpenRouter refinement ----
        try:
            logger.info("LLMService Stream: All cloud endpoints failed. Using local Prometheus + refinement...")
            local_result = LLMService._call_local_prometheus(prompt, system_prompt, max_tokens, temperature)
            refined_text, _, _ = LLMService._refine_prompt(local_result, prompt, system_prompt)
            yield refined_text
        except Exception as e:
            logger.error(f"LLMService Stream: Prometheus pipeline failed: {e}")
            yield f"\n[Error] All generation tiers failed: {str(e)}"
