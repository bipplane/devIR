"""
Agent State Definition

This module defines the state schema that flows through the LangGraph workflow.
The state acts as the agent's "short-term memory" - tracking the investigation
progress, findings, and decisions at each step.
"""

from typing import TypedDict, List, Optional, Literal
from dataclasses import dataclass, field


class AgentState(TypedDict):
    """
    The central state object that gets passed between all nodes in the graph.
    
    This is the "brain" of the agent - every node can read from and write to
    specific fields, enabling information flow through the investigation pipeline.
    """
    
    # Input
    error_log: str  # The raw error message/stack trace from the user
    
    # Diagnostic Phase
    error_type: str  # Categorised error type (database, network, code, config, etc.)
    error_summary: str  # Human-readable summary of what went wrong
    affected_components: List[str]  # List of likely affected system components
    
    # Research Phase
    search_queries: List[str]  # Generated search queries for investigation
    research_findings: List[str]  # Results from web searches
    relevant_docs: List[str]  # Extracted relevant documentation snippets
    
    # Code Audit Phase
    files_to_check: List[str]  # File paths that might be related to the error
    code_context: str  # Relevant code snippets from the codebase
    
    # Solution Phase
    proposed_solution: str  # The agent's proposed fix
    solution_confidence: float  # Confidence score 0.0 - 1.0
    solution_steps: List[str]  # Step-by-step implementation guide
    code_changes: str  # Suggested code modifications
    
    # Control Flow
    iterations: int  # Number of research cycles completed
    max_iterations: int  # Maximum allowed iterations (prevents infinite loops)
    needs_human_approval: bool  # Flag for human-in-the-loop checkpoint
    pending_action: str  # Description of action awaiting approval
    
    # Conversation History
    messages: List[str]  # Log of agent's reasoning at each step
    
    # Status
    status: Literal["investigating", "researching", "auditing", "solving", "awaiting_approval", "complete", "failed"]


def create_initial_state(error_log: str, max_iterations: int = 3) -> AgentState:
    """
    Factory function to create a fresh agent state with sensible defaults.
    
    Args:
        error_log: The error message or stack trace to investigate
        max_iterations: Maximum research cycles before forcing a conclusion
    
    Returns:
        A properly initialised AgentState
    """
    return AgentState(
        error_log=error_log,
        error_type="unknown",
        error_summary="",
        affected_components=[],
        search_queries=[],
        research_findings=[],
        relevant_docs=[],
        files_to_check=[],
        code_context="",
        proposed_solution="",
        solution_confidence=0.0,
        solution_steps=[],
        code_changes="",
        iterations=0,
        max_iterations=max_iterations,
        needs_human_approval=False,
        pending_action="",
        messages=[],
        status="investigating"
    )
