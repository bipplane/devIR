"""
Workflow Graph Module

Defines the LangGraph workflow that orchestrates the incident response agent.
This is where the state machine is constructed with nodes and edges.
"""

from typing import Optional
from langgraph.graph import StateGraph, END

from .state import AgentState, create_initial_state
from .nodes import NodeFactory, should_continue_research, check_solution_confidence
from .llm import BaseLLM, get_llm
from .tools import TavilySearchTool, FileReaderTool


def create_incident_responder_graph(
    llm: Optional[BaseLLM] = None,
    search_tool: Optional[TavilySearchTool] = None,
    file_tool: Optional[FileReaderTool] = None,
    verbose: bool = True
) -> StateGraph:
    """
    Create the incident responder workflow graph.
    
    This function builds the complete state machine for investigating
    and resolving errors. The graph looks like:
    
    ┌─────────────┐
    │   START     │
    └──────┬──────┘
           │
           ▼
    ┌─────────────┐
    │ Diagnostician│ ──► Analyse error, categorise, generate search queries
    └──────┬──────┘
           │
           ▼
    ┌─────────────┐     ┌────────────────┐
    │ Researcher  │ ◄───┤ Loop back if   │
    └──────┬──────┘     │ need more info │
           │            └────────────────┘
           ▼
    ┌─────────────┐
    │ Code Auditor│ ──► Examine relevant code files
    └──────┬──────┘
           │
           ▼
    ┌─────────────┐     ┌────────────────┐
    │   Solver    │ ────┤ Back to research│
    └──────┬──────┘     │ if low confidence│
           │            └────────────────┘
           ▼
    ┌─────────────┐
    │Human Approval│ ──► Optional checkpoint for risky operations
    └──────┬──────┘
           │
           ▼
    ┌─────────────┐
    │    END      │
    └─────────────┘
    
    Args:
        llm: The language model to use (defaults to Gemini)
        search_tool: Tavily search tool instance
        file_tool: File reader tool instance
        verbose: Whether to print progress messages
        
    Returns:
        A compiled LangGraph workflow ready to execute
    """
    
    # Create node factory with dependencies
    factory = NodeFactory(
        llm=llm,
        search_tool=search_tool,
        file_tool=file_tool,
        verbose=verbose
    )
    
    # Initialise the state graph
    workflow = StateGraph(AgentState)
    
    # ==========================================================================
    # ADD NODES
    # ==========================================================================
    
    workflow.add_node("diagnose", factory.diagnostician)
    workflow.add_node("research", factory.researcher)
    workflow.add_node("audit", factory.code_auditor)
    workflow.add_node("solve", factory.solver)
    workflow.add_node("human_approval", factory.human_approval)
    
    # ==========================================================================
    # SET ENTRY POINT
    # ==========================================================================
    
    workflow.set_entry_point("diagnose")
    
    # ==========================================================================
    # ADD EDGES (The Control Flow)
    # ==========================================================================
    
    # Diagnosis always leads to research
    workflow.add_edge("diagnose", "research")
    
    # Research can loop back to itself or proceed to audit
    workflow.add_conditional_edges(
        "research",
        should_continue_research,
        {
            "research": "research",  # Loop back for more research
            "audit": "audit"          # Proceed to code audit
        }
    )
    
    # Audit leads to solver
    workflow.add_edge("audit", "solve")
    
    # Solver has conditional paths based on confidence and approval needs
    workflow.add_conditional_edges(
        "solve",
        check_solution_confidence,
        {
            "refine": "research",        # Low confidence → more research
            "approve": "human_approval", # Needs human approval
            "end": END                   # Confident solution → finish
        }
    )
    
    # Human approval leads to end
    workflow.add_edge("human_approval", END)
    
    return workflow


def compile_graph(workflow: StateGraph):
    """
    Compile the workflow graph into an executable application.
    
    Args:
        workflow: The StateGraph to compile
        
    Returns:
        A compiled graph ready for execution
    """
    return workflow.compile()


class IncidentResponder:
    """
    High-level interface for the Incident Responder agent.
    
    This class provides a clean API for creating and running the
    incident investigation workflow.
    """
    
    def __init__(
        self,
        llm_provider: str = "gemini",
        llm_model: Optional[str] = None,
        base_directory: Optional[str] = None,
        tavily_api_key: Optional[str] = None,
        verbose: bool = True
    ):
        """
        Initialise the incident responder.
        
        Args:
            llm_provider: LLM provider (currently only "gemini" is supported)
            llm_model: Specific model to use (uses provider default if None)
            base_directory: Root directory for file operations
            tavily_api_key: API key for Tavily search
            verbose: Whether to print progress messages
        """
        # Initialise LLM
        llm_kwargs = {}
        if llm_model:
            llm_kwargs["model"] = llm_model
        self.llm = get_llm(llm_provider, **llm_kwargs)
        
        # Initialise tools
        self.search_tool = TavilySearchTool(api_key=tavily_api_key)
        self.file_tool = FileReaderTool(base_directory=base_directory)
        
        self.verbose = verbose
        
        # Build and compile the graph
        self.workflow = create_incident_responder_graph(
            llm=self.llm,
            search_tool=self.search_tool,
            file_tool=self.file_tool,
            verbose=verbose
        )
        self.app = compile_graph(self.workflow)
    
    def investigate(self, error_log: str, max_iterations: int = 3) -> AgentState:
        """
        Investigate an error and propose a solution.
        
        Args:
            error_log: The error message or stack trace to investigate
            max_iterations: Maximum research iterations before concluding
            
        Returns:
            The final AgentState with the investigation results
        """
        # Create initial state
        initial_state = create_initial_state(
            error_log=error_log,
            max_iterations=max_iterations
        )
        
        if self.verbose:
            print("\n" + "="*60)
            print("INCIDENT RESPONDER AGENT STARTING")
            print("="*60)
            print(f"\nInput Error Log:\n{error_log[:500]}...")
        
        # Execute the workflow
        try:
            final_state = self.app.invoke(initial_state)
        except Exception as e:
            if self.verbose:
                print(f"\nAgent encountered an error: {e}")
            raise
        
        if self.verbose:
            self._print_summary(final_state)
        
        return final_state
    
    def _print_summary(self, state: AgentState):
        """Print a summary of the investigation results."""
        print("\n" + "="*60)
        print("INVESTIGATION SUMMARY")
        print("="*60)
        
        print(f"\nError Type: {state.get('error_type', 'unknown')}")
        print(f"Summary: {state.get('error_summary', 'N/A')}")
        print(f"Research Iterations: {state.get('iterations', 0)}")
        print(f"Solution Confidence: {state.get('solution_confidence', 0):.0%}")
        
        print("\n" + "-"*40)
        print("PROPOSED SOLUTION")
        print("-"*40)
        print(state.get("proposed_solution", "No solution generated"))
        
        if state.get("solution_steps"):
            print("\n" + "-"*40)
            print("STEPS TO IMPLEMENT")
            print("-"*40)
            for i, step in enumerate(state["solution_steps"], 1):
                print(f"  {i}. {step}")
        
        if state.get("code_changes"):
            print("\n" + "-"*40)
            print("CODE CHANGES")
            print("-"*40)
            print(state["code_changes"])
        
        if state.get("needs_human_approval"):
            print("\n" + "="*40)
            print("HUMAN APPROVAL REQUIRED")
            print("="*40)
            print(f"Reason: {state.get('pending_action', 'No details')}")
        
        print("\n" + "="*60)


def quick_investigate(error_log: str, **kwargs) -> AgentState:
    """
    Convenience function to quickly investigate an error.
    
    Args:
        error_log: The error to investigate
        **kwargs: Additional arguments passed to IncidentResponder
        
    Returns:
        The final investigation state
    """
    responder = IncidentResponder(**kwargs)
    return responder.investigate(error_log)
