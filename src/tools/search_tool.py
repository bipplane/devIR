"""
Tavily Search Tool

Provides web search capabilities optimised for AI agents.
Tavily is specifically designed for LLM applications and returns
clean, relevant results without the noise of traditional search engines.
"""

import os
from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class SearchResult:
    """Represents a single search result."""
    title: str
    url: str
    content: str
    score: float


class TavilySearchTool:
    """
    Web search tool using Tavily API.
    
    Tavily provides:
    - Clean, summarised results (no ads/spam)
    - Relevance scoring
    - Optional deep research mode
    - Perfect for technical documentation searches
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialise the Tavily search tool.
        
        Args:
            api_key: Tavily API key. If not provided, reads from TAVILY_API_KEY env var.
        """
        self.api_key = api_key or os.getenv("TAVILY_API_KEY")
        self._client = None
        
    def _get_client(self):
        """Lazy initialisation of Tavily client."""
        if self._client is None:
            if not self.api_key:
                raise ValueError(
                    "Tavily API key not found. Set TAVILY_API_KEY environment variable "
                    "or pass api_key to constructor. Get a free key at https://tavily.com"
                )
            try:
                from tavily import TavilyClient
                self._client = TavilyClient(api_key=self.api_key)
            except ImportError:
                raise ImportError(
                    "tavily-python package not installed. Run: pip install tavily-python"
                )
        return self._client
    
    def search(
        self,
        query: str,
        search_depth: str = "basic",
        max_results: int = 5,
        include_domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None
    ) -> List[SearchResult]:
        """
        Execute a web search query.
        
        Args:
            query: The search query string
            search_depth: "basic" for quick searches, "advanced" for deeper research
            max_results: Maximum number of results to return
            include_domains: Limit search to these domains (e.g., ["stackoverflow.com"])
            exclude_domains: Exclude these domains from results
            
        Returns:
            List of SearchResult objects with title, url, content, and relevance score
        """
        client = self._get_client()
        
        # Build search parameters
        search_params = {
            "query": query,
            "search_depth": search_depth,
            "max_results": max_results,
        }
        
        if include_domains:
            search_params["include_domains"] = include_domains
        if exclude_domains:
            search_params["exclude_domains"] = exclude_domains
            
        # Execute search
        response = client.search(**search_params)
        
        # Parse results
        results = []
        for item in response.get("results", []):
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                content=item.get("content", ""),
                score=item.get("score", 0.0)
            ))
            
        return results
    
    def search_technical(self, query: str, max_results: int = 5) -> List[SearchResult]:
        """
        Specialised search for technical/programming queries.
        Prioritises StackOverflow, GitHub, and official documentation.
        
        Args:
            query: Technical search query
            max_results: Maximum results to return
            
        Returns:
            List of SearchResult objects from technical sources
        """
        return self.search(
            query=query,
            search_depth="advanced",
            max_results=max_results,
            include_domains=[
                "stackoverflow.com",
                "github.com",
                "docs.python.org",
                "docs.docker.com",
                "kubernetes.io",
                "aws.amazon.com/documentation",
                "cloud.google.com/docs",
                "learn.microsoft.com",
                "developer.mozilla.org"
            ]
        )
    
    def format_results(self, results: List[SearchResult]) -> str:
        """
        Format search results into a readable string for the LLM.
        
        Args:
            results: List of SearchResult objects
            
        Returns:
            Formatted string with all results
        """
        if not results:
            return "No search results found."
            
        formatted = []
        for i, result in enumerate(results, 1):
            formatted.append(f"""
--- Result {i} ---
Title: {result.title}
URL: {result.url}
Relevance: {result.score:.2f}
Content: {result.content}
""")
        
        return "\n".join(formatted)
