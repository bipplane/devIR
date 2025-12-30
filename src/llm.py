"""
LLM Interface

Provides an interface for interacting with Google Gemini.
"""

import os
from typing import Optional
from abc import ABC, abstractmethod


class BaseLLM(ABC):
    """Abstract base class for LLM providers."""
    
    @abstractmethod
    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate a response from the LLM."""
        pass


class GeminiLLM(BaseLLM):
    """Google Gemini interface using google-genai SDK."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemini-2.5-flash-lite"
    ):
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        self.model = model
        self._client = None
        
    def _get_client(self):
        if self._client is None:
            if not self.api_key:
                raise ValueError("Google API key not found. Set GOOGLE_API_KEY environment variable.")
            try:
                from google import genai
                self._client = genai.Client(api_key=self.api_key)
            except ImportError:
                raise ImportError("google-genai package not installed. Run: pip install google-genai")
        return self._client
    
    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        client = self._get_client()
        
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"
            
        response = client.models.generate_content(
            model=self.model,
            contents=full_prompt
        )
        return response.text


def get_llm(provider: str = "gemini", **kwargs) -> BaseLLM:
    """
    Factory function to get an LLM instance.
    
    Args:
        provider: Currently only "gemini" is supported
        **kwargs: Additional arguments passed to the LLM constructor
        
    Returns:
        An LLM instance
    """
    providers = {
        "gemini": GeminiLLM
    }
    
    if provider not in providers:
        raise ValueError(f"Unknown provider: {provider}. Choose from: {list(providers.keys())}")
        
    return providers[provider](**kwargs)
