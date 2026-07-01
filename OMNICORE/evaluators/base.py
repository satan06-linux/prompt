import abc
from typing import Dict, Any

class BaseEvaluator(abc.ABC):
    """Abstract base class for evaluation components (Structural, Rule, LLM Judge)."""
    
    @abc.abstractmethod
    def evaluate(self, generated_prompt: str, benchmark_task: Dict[str, Any], rubric: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate the generated prompt against the benchmark task criteria.
        Returns a dictionary containing scores and feedback.
        """
        pass
