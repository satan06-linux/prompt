from typing import Dict, Any, List
from .base import BaseEvaluator
from .structural import StructuralValidator
from .rule import RuleValidator
from .llm_judge import LLMJudge
from prometheus.providers.base import BaseProvider

class CompositeEvaluator(BaseEvaluator):
    """Orchestrates the hybrid evaluation pipeline."""
    
    def __init__(self, provider: BaseProvider):
        self.structural = StructuralValidator()
        self.rule = RuleValidator()
        self.llm_judge = LLMJudge(provider)
        
    def evaluate(self, generated_prompt: str, benchmark_task: Dict[str, Any], rubric: Dict[str, Any]) -> Dict[str, Any]:
        
        # 1. Structural
        struct_res = self.structural.evaluate(generated_prompt, benchmark_task, rubric)
        
        # 2. Rule
        rule_res = self.rule.evaluate(generated_prompt, benchmark_task, rubric)
        
        # 3. LLM Judge
        llm_res = self.llm_judge.evaluate(generated_prompt, benchmark_task, rubric)
        
        total_score = struct_res["score"] + rule_res["score"] + llm_res["score"]
        total_max = struct_res["max_score"] + rule_res["max_score"] + llm_res["max_score"]
        
        # Ensure it caps at 100
        total_score = min(total_score, 100.0)
        
        return {
            "final_score": round(total_score, 2),
            "max_score": round(total_max, 2),
            "breakdown": {
                "structural": struct_res,
                "rule": rule_res,
                "llm_judge": llm_res
            },
            "feedback": struct_res["feedback"] + rule_res["feedback"] + llm_res["feedback"]
        }
