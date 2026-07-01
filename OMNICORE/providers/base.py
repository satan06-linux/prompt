import abc
from typing import Dict, Any, List

class BaseProvider(abc.ABC):
    """Abstract base class for all LLM providers (local or remote)."""
    
    @abc.abstractmethod
    def generate(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        """Generate a response given a system and user prompt."""
        pass
    
    @abc.abstractmethod
    def get_metadata(self) -> Dict[str, Any]:
        """Return provider metadata (name, model, constraints, etc)."""
        pass
