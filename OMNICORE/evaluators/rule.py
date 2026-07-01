from typing import Dict, Any
from .base import BaseEvaluator

class RuleValidator(BaseEvaluator):
    """Deterministic validator for constraints, word counts, and expected characteristics."""
    
    def evaluate(self, generated_prompt: str, benchmark_task: Dict[str, Any], rubric: Dict[str, Any]) -> Dict[str, Any]:
        weights = benchmark_task.get("evaluation_weights", {})
        max_constraints = float(weights.get("constraints", 20))
        
        results = {
            "score": 0.0,
            "max_score": max_constraints,
            "feedback": [],
            "violations": []
        }
        
        prompt_lower = generated_prompt.lower()
        
        # Check success criteria minimums (heuristic mapping)
        success_criteria = benchmark_task.get("success_criteria", {})
        min_reqs = success_criteria.get("minimum_requirements", [])
        
        passed_reqs = 0
        for req in min_reqs:
            # Very basic heuristic for minimum requirements
            words = set(req.lower().replace("-", " ").split())
            important_words = {w for w in words if len(w) > 4}
            
            if any(w in prompt_lower for w in important_words):
                passed_reqs += 1
            else:
                results["violations"].append(f"Failed min requirement: {req}")
                
        # Check expected characteristics
        characteristics = benchmark_task.get("expected_prompt_characteristics", [])
        passed_chars = 0
        for char in characteristics:
            words = set(char.lower().replace("-", " ").split())
            important_words = {w for w in words if len(w) > 4}
            if any(w in prompt_lower for w in important_words):
                passed_chars += 1
            else:
                results["violations"].append(f"Missed characteristic: {char}")
                
        total_checks = len(min_reqs) + len(characteristics)
        total_passed = passed_reqs + passed_chars
        
        ratio = total_passed / total_checks if total_checks > 0 else 1.0
        results["score"] = round(max_constraints * ratio, 2)
        
        if results["violations"]:
            results["feedback"].append(f"Rule violations found: {len(results['violations'])}")
        else:
            results["feedback"].append("All deterministic rules passed successfully.")
            
        return results
