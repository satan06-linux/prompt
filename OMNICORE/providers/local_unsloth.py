import os
import sys
import torch
from typing import Dict, Any
from .base import BaseProvider

class LocalUnslothProvider(BaseProvider):
    def __init__(self, model_name: str = "unsloth/gemma-4-E4B-it", weights_path: str = None):
        self.base_model_name = model_name
        self.weights_path = weights_path
        self.model = None
        self.tokenizer = None
        
        self._load_model()
        
    def _load_model(self):
        try:
            from unsloth import FastLanguageModel
        except ImportError:
            raise ImportError("Unsloth is not installed. Please install it to use LocalUnslothProvider.")

        load_path = self.weights_path if (self.weights_path and os.path.exists(self.weights_path)) else self.base_model_name
        
        print(f"💡 LocalUnslothProvider: Loading model from {load_path}...")
        
        self.model, self.tokenizer = FastLanguageModel.from_pretrained(
            model_name=load_path,
            max_seq_length=2048,
            dtype=torch.float16,
            load_in_4bit=True,
        )
        FastLanguageModel.for_inference(self.model)
        
    def generate(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        max_tokens = kwargs.get("max_tokens", 1024)
        temperature = kwargs.get("temperature", 0.7)
        
        # Format conversation for Gemma Instruction Tuning
        prompt = f"<|system|>\n{system_prompt}\n<|end|>\n<|user|>\n{user_prompt}\n<|end|>\n<|assistant|>\n"
        
        inputs = self.tokenizer(prompt, return_tensors="pt").to("cuda")
        
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=max_tokens,
                temperature=temperature,
                use_cache=True,
                pad_token_id=self.tokenizer.eos_token_id
            )
            
        decoded = self.tokenizer.decode(outputs[0][inputs["input_ids"].shape[-1]:], skip_special_tokens=True)
        return decoded.strip()
        
    def get_metadata(self) -> Dict[str, Any]:
        return {
            "provider": "Unsloth (Local)",
            "model": self.base_model_name,
            "weights": self.weights_path if (self.weights_path and os.path.exists(self.weights_path)) else "base",
            "type": "local"
        }
