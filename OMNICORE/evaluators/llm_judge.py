import json
import re
from typing import Dict, Any
from .base import BaseEvaluator
from prometheus.providers.base import BaseProvider

class LLMJudge(BaseEvaluator):
    """Subjective LLM-as-a-Judge for clarity, accuracy, and creativity."""
    
    def __init__(self, provider: BaseProvider):
        self.provider = provider

    def evaluate(self, generated_prompt: str, benchmark_task: Dict[str, Any], rubric: Dict[str, Any]) -> Dict[str, Any]:
        weights = benchmark_task.get("evaluation_weights", {})
        
        # We handle structure and constraints in the deterministic validators
        # LLM Judge handles: accuracy, clarity, creativity
        max_accuracy = float(weights.get("accuracy", 20))
        max_clarity = float(weights.get("clarity", 20))
        max_creativity = float(weights.get("creativity", 20))
        
        total_judge_score = max_accuracy + max_clarity + max_creativity
        
        if total_judge_score == 0:
            return {"score": 0.0, "max_score": 0.0, "feedback": ["No subjective weights."]}

        system_prompt = (
            "You are an expert AI Prompt Engineer and Evaluator. "
            "You must score the provided generated prompt based on the user's goal. "
            "Return ONLY a valid JSON object with scores between 0.0 and the max allowed for each category, "
            "plus a short 'feedback' string."
        )
        
        user_prompt = f"""
Task Goal: {benchmark_task.get("user_goal")}
Target AI: {benchmark_task.get("primary_target")}

Generated Prompt:
{generated_prompt}

Scoring Rubric:
- Accuracy (Max {max_accuracy}): Does it solve the exact problem?
- Clarity (Max {max_clarity}): Is it easy for the target AI to understand?
- Creativity (Max {max_creativity}): Does it use advanced techniques (personas, chain of thought)?

Expected Output Format EXACTLY:
{{
  "accuracy": 15.5,
  "clarity": 18.0,
  "creativity": 12.0,
  "feedback": "Clear prompt but lacks advanced reasoning techniques."
}}
"""
        try:
            response = self.provider.generate(system_prompt, user_prompt, max_tokens=200, temperature=0.1)
            
            if not response or not response.strip():
                raise ValueError("Provider returned an empty response.")
                
            # Extract JSON
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
            else:
                data = json.loads(response)
                
            acc = float(data.get("accuracy", max_accuracy * 0.5))
            clar = float(data.get("clarity", max_clarity * 0.5))
            cre = float(data.get("creativity", max_creativity * 0.5))
            
            # Clamp scores
            acc = min(max(acc, 0.0), max_accuracy)
            clar = min(max(clar, 0.0), max_clarity)
            cre = min(max(cre, 0.0), max_creativity)
            
            total = acc + clar + cre
            
            return {
                "score": round(total, 2),
                "max_score": total_judge_score,
                "breakdown": {
                    "accuracy": acc,
                    "clarity": clar,
                    "creativity": cre
                },
                "feedback": [data.get("feedback", "No feedback provided.")]
            }
            
        except Exception as e:
            # Fallback on failure
            print(f"⚠️ LLM Judge failed: {e}")
            fallback = (total_judge_score) * 0.7
            return {
                "score": round(fallback, 2),
                "max_score": total_judge_score,
                "breakdown": {},
                "feedback": ["LLM Judge failed, applied 70% fallback score."]
            }
