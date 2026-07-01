import re
from typing import Dict, Any
from .base import BaseEvaluator

class StructuralValidator(BaseEvaluator):
    """Deterministic validator for structural prompt elements (headings, JSON, markdown, etc.)."""
    
    def evaluate(self, generated_prompt: str, benchmark_task: Dict[str, Any], rubric: Dict[str, Any]) -> Dict[str, Any]:
        expected_sections = benchmark_task.get("expected_prompt_sections", [])
        expected_output = benchmark_task.get("expected_output", "text")
        
        results = {
            "score": 0.0,
            "max_score": float(benchmark_task.get("evaluation_weights", {}).get("structure", 20)),
            "feedback": [],
            "missing_sections": []
        }
        
        # Check expected sections
        found_sections = 0
        prompt_lower = generated_prompt.lower()
        for section in expected_sections:
            if section.lower() in prompt_lower:
                found_sections += 1
            else:
                results["missing_sections"].append(section)
                
        section_score_ratio = found_sections / len(expected_sections) if expected_sections else 1.0
        
        # Check output format indicators
        format_valid = True
        if expected_output == "json":
            if "{" not in generated_prompt and "json" not in prompt_lower:
                format_valid = False
                results["feedback"].append("Missing JSON structural indicators.")
        elif expected_output == "markdown":
            if "#" not in generated_prompt and "markdown" not in prompt_lower:
                format_valid = False
                results["feedback"].append("Missing markdown structural indicators.")
                
        # Calculate final structural score
        format_multiplier = 1.0 if format_valid else 0.5
        results["score"] = round((results["max_score"] * section_score_ratio) * format_multiplier, 2)
        
        if results["missing_sections"]:
            results["feedback"].append(f"Missing sections: {', '.join(results['missing_sections'])}")
            
        if not results["feedback"]:
            results["feedback"].append("Excellent structural formatting.")
            
        return results
