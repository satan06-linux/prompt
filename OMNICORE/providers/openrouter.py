import os
import sys
import time
import httpx
from typing import Dict, Any
from .base import BaseProvider

# Import root config to get API keys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
try:
    import config
except ImportError:
    pass

class OpenRouterProvider(BaseProvider):
    def __init__(self, model: str = "google/gemini-2.5-flash", api_key: str = None):
        self.model = model
        self.api_key = api_key or getattr(config, "OPEN_ROUTER_API_KEY", os.environ.get("OPEN_ROUTER_API_KEY"))
        if not self.api_key:
            raise ValueError("OPEN_ROUTER_API_KEY must be provided")
        
        self.url = "https://openrouter.ai/api/v1/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://nexafian.com",
            "X-Title": "Nexafian Prometheus"
        }

    def generate(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        max_tokens = kwargs.get("max_tokens", 4000)
        temperature = kwargs.get("temperature", 0.7)
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": temperature
        }

        for attempt in range(3):
            try:
                response = httpx.post(self.url, headers=self.headers, json=payload, timeout=60.0)
                if response.status_code == 200:
                    return response.json()["choices"][0]["message"]["content"].strip()
                elif response.status_code == 429:
                    time.sleep((attempt + 1) * 5)
                else:
                    time.sleep(2)
            except Exception:
                time.sleep(2)
                
        return ""

    def get_metadata(self) -> Dict[str, Any]:
        return {
            "provider": "OpenRouter",
            "model": self.model,
            "type": "remote"
        }
