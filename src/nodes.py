"""
Graph Nodes Module v2.0

Contains all the node functions for the LangGraph workflow.
Each node represents a step in the incident investigation pipeline.
Uses JSON parsing for structured LLM outputs.
"""

import re
import json
from typing import Dict, Any, Optional, List
from .state import AgentState
from .llm import BaseLLM, get_llm
from .tools import TavilySearchTool, FileReaderTool
from . import prompts


def parse_json_response(response: str) -> Dict[str, Any]:
    """
    Parse a JSON response from the LLM.
    
    Handles common issues like:
    - <thinking> tags before JSON
    - Markdown code blocks around JSON
    - Trailing text after JSON
    
    Args:
        response: The raw LLM response text
        
    Returns:
        Parsed JSON as a dictionary
    """
    # Remove <thinking>...</thinking> blocks
    cleaned = re.sub(r'<thinking>.*?</thinking>', '', response, flags=re.DOTALL)
    
    # Remove markdown code blocks
    cleaned = re.sub(r'```json\s*', '', cleaned)
    cleaned = re.sub(r'```\s*', '', cleaned)
    
    # Find JSON object in the response
    # Look for the first { and last }
    start = cleaned.find('{')
    end = cleaned.rfind('}')
    
    if start != -1 and end != -1 and end > start:
        json_str = cleaned[start:end + 1]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass
    
    # Fallback: return empty dict if parsing fails
    return {}


def parse_llm_response(response: str, fields: List[str]) -> Dict[str, str]:
    """
    Legacy parser for structured LLM responses.
    Falls back to this if JSON parsing fails.
    
    Args:
        response: The raw LLM response text
        fields: List of field names to extract
        
    Returns:
        Dictionary of field_name -> value
    """
    result = {}
    
    for field in fields:
        # Pattern: FIELD_NAME: value (until next field or end)
        pattern = rf"{field}:\s*(.+?)(?=\n[A-Z_]+:|$)"
        match = re.search(pattern, response, re.DOTALL | re.IGNORECASE)
        if match:
            value = match.group(1).strip()
            # Clean up list formatting
            if value.startswith("[") and value.endswith("]"):
                value = value[1:-1]
            result[field.lower()] = value
        else:
            result[field.lower()] = ""
            
    return result


class NodeFactory:
    """
    Factory class that creates node functions with injected dependencies.
    This allows for easier testing and configuration.
    """
    
    def __init__(
        self,
        llm: Optional[BaseLLM] = None,
        search_tool: Optional[TavilySearchTool] = None,
        file_tool: Optional[FileReaderTool] = None,
        verbose: bool = True
    ):
        """
        Initialise the node factory with dependencies.
        
        Args:
            llm: The LLM to use for reasoning (defaults to Gemini)
            search_tool: Tavily search tool instance
            file_tool: File reader tool instance
            verbose: Whether to print progress messages
        """
        self.llm = llm or get_llm("gemini")
        self.search_tool = search_tool or TavilySearchTool()
        self.file_tool = file_tool or FileReaderTool()
        self.verbose = verbose
        
    def _log(self, message: str):
        """Print a log message if verbose mode is enabled."""
        if self.verbose:
            print(message)
    
    # =========================================================================
    # NODE 1: DIAGNOSTICIAN
    # =========================================================================
    
    def diagnostician(self, state: AgentState) -> Dict[str, Any]:
        """
        Analyse the error log and categorise the issue.
        
        This is the entry point of the investigation. It examines the raw
        error and produces a structured understanding of what went wrong.
        """
        self._log("\n" + "="*60)
        self._log("DIAGNOSTICIAN NODE - Analysing error...")
        self._log("="*60)
        
        # Build the prompt
        prompt = prompts.DIAGNOSTICIAN_PROMPT.format(
            error_log=state["error_log"]
        )
        
        # Call LLM for analysis
        response = self.llm.generate(
            prompt=prompt,
            system_prompt=prompts.DIAGNOSTICIAN_SYSTEM
        )
        
        # Parse JSON response (with fallback to legacy parsing)
        parsed = parse_json_response(response)
        
        if not parsed:
            # Fallback to legacy text parsing
            parsed = parse_llm_response(response, [
                "ERROR_TYPE",
                "ERROR_SUMMARY", 
                "AFFECTED_COMPONENTS",
                "SEARCH_QUERIES",
                "FILES_TO_CHECK",
                "SEVERITY",
                "IMMEDIATE_ACTIONS"
            ])
            # Legacy parsing returns strings, need to split into lists
            search_queries = [
                q.strip() 
                for q in parsed.get("search_queries", "").split(",")
                if q.strip()
            ]
            files_to_check = [
                f.strip().strip('"').strip("'")
                for f in parsed.get("files_to_check", "").split(",")
                if f.strip()
            ]
            affected_components = [
                c.strip()
                for c in parsed.get("affected_components", "").split(",")
                if c.strip()
            ]
        else:
            # JSON parsing returns proper types
            search_queries = parsed.get("search_keywords", [])
            files_to_check = parsed.get("files_to_check", [])
            affected_components = parsed.get("affected_components", [])
        
        # Log the findings
        error_type = parsed.get("error_type", "unknown")
        error_summary = parsed.get("error_summary", "N/A")
        
        self._log(f"\n[OK] Error Type: {error_type}")
        self._log(f"Summary: {error_summary}")
        if search_queries:
            self._log("Will search for:")
            for i, q in enumerate(search_queries[:3], 1):
                self._log(f"  {i}. {q}")
        
        # Return state updates
        return {
            "error_type": error_type,
            "error_summary": error_summary,
            "affected_components": affected_components,
            "search_queries": search_queries[:5],
            "files_to_check": files_to_check,
            "messages": state.get("messages", []) + [f"[Diagnostician] {response}"],
            "status": "researching"
        }
    
    # =========================================================================
    # NODE 2: WEBSCRAPER
    # =========================================================================
    
    def webscraper(self, state: AgentState) -> Dict[str, Any]:
        """
        Search the web for solutions and relevant documentation.
        
        Uses Tavily to find StackOverflow threads, GitHub issues, and
        documentation that might help solve the issue.
        """
        self._log("\n" + "="*60)
        self._log("WEBSCRAPER NODE - Searching for solutions...")
        self._log("="*60)
        
        all_results = []
        queries = state.get("search_queries", [])
        
        if queries:
            self._log("\nSearching:")
            for query in queries:
                self._log(f'  - "{query}"')
        
        # Execute each search query
        for query in queries:
            try:
                results = self.search_tool.search_technical(query, max_results=5)
                for result in results:
                    all_results.append(f"[{result.title}]({result.url})\n{result.content}")
                    self._log(f"  Found: {result.title}")
                    self._log(f"         {result.url}")
            except Exception as e:
                self._log(f"  [WARN] Search failed: {e}")
                all_results.append(f"Search for '{query}' failed: {str(e)}")
        
        # Format results for LLM
        search_results_text = "\n\n---\n\n".join(all_results) if all_results else "No search results found."
        
        # Ask LLM to analyse findings
        prompt = prompts.WEBSCRAPER_PROMPT.format(
            error_summary=state.get("error_summary", ""),
            error_type=state.get("error_type", "unknown"),
            search_results=search_results_text
        )
        
        response = self.llm.generate(
            prompt=prompt,
            system_prompt=prompts.WEBSCRAPER_SYSTEM
        )
        
        # Parse JSON response (with fallback)
        parsed = parse_json_response(response)
        
        if not parsed:
            # Fallback to legacy text parsing
            parsed = parse_llm_response(response, [
                "RELEVANT_FINDINGS",
                "COMMON_SOLUTIONS",
                "POTENTIAL_PITFALLS",
                "CONFIDENCE_LEVEL",
                "NEED_MORE_RESEARCH",
                "REFINED_QUERY"
            ])
            need_more = parsed.get("need_more_research", "no").lower() == "yes"
            refined_query = parsed.get("refined_query", "")
            new_findings = [
                parsed.get("relevant_findings", ""),
                parsed.get("common_solutions", "")
            ]
        else:
            # JSON response
            need_more = parsed.get("needs_more_research", False)
            refined_query = parsed.get("refined_query") or ""
            
            # Format solutions with source attribution
            solutions = parsed.get("relevant_solutions", [])
            findings_text = "\n".join([
                f"- {s.get('solution_summary', '')} (Source: {s.get('source_url', 'unknown')}, Confidence: {s.get('confidence', 'unknown')})"
                for s in solutions
            ])
            patterns = ", ".join(parsed.get("common_patterns", []))
            warnings = ", ".join(parsed.get("warnings", []))
            
            new_findings = [
                f"Solutions:\n{findings_text}",
                f"Common patterns: {patterns}",
                f"Warnings: {warnings}"
            ]
        
        # Update research findings
        existing_findings = state.get("research_findings", [])
        
        # Handle refinement loop
        iterations = state.get("iterations", 0) + 1
        max_iterations = state.get("max_iterations", 3)
        
        # If we need more research and haven't hit max iterations
        if need_more and refined_query and iterations < max_iterations:
            self._log(f"\nNeed more research (iteration {iterations}/{max_iterations})")
            self._log(f"   Refined query: {refined_query}")
            
            return {
                "research_findings": existing_findings + new_findings,
                "search_queries": [refined_query],
                "iterations": iterations,
                "messages": state.get("messages", []) + [f"[Webscraper] {response}"],
                "status": "researching"  # Stay in research loop
            }
        
        self._log(f"\n[OK] Research complete after {iterations} iteration(s)")
        
        return {
            "research_findings": existing_findings + new_findings,
            "relevant_docs": [search_results_text],
            "iterations": iterations,
            "messages": state.get("messages", []) + [f"[Webscraper] {response}"],
            "status": "auditing"
        }
    
    # =========================================================================
    # NODE 3: CODE AUDITOR
    # =========================================================================
    
    def code_auditor(self, state: AgentState) -> Dict[str, Any]:
        """
        Examine relevant code files to find the root cause.
        
        Reads code files that might be related to the error and analyses
        them in context of the diagnosis and research findings.
        """
        self._log("\n" + "="*60)
        self._log("CODE AUDITOR NODE - Examining code files...")
        self._log("="*60)
        
        files_to_check = state.get("files_to_check", [])
        code_context = ""
        
        if files_to_check:
            # Try to find and read the files
            for file_pattern in files_to_check:
                self._log(f"\nLooking for: {file_pattern}")
                
                try:
                    # Try to find files matching the pattern
                    matches = self.file_tool.find_files([f"**/{file_pattern}", f"**/*{file_pattern}*"])
                    
                    for match in matches[:2]:  # Limit to 2 files per pattern
                        self._log(f"  Reading: {match}")
                        try:
                            content = self.file_tool.read_file(match)
                            code_context += self.file_tool.format_file_content(content)
                        except Exception as e:
                            self._log(f"  [WARN] Could not read: {e}")
                            
                except Exception as e:
                    self._log(f"  [WARN] Search failed: {e}")
        
        if not code_context:
            code_context = "No relevant code files found or accessible."
            self._log("\n[WARN] No code files found to audit")
        
        # Ask LLM to analyse the code
        prompt = prompts.CODE_AUDITOR_PROMPT.format(
            error_summary=state.get("error_summary", ""),
            error_type=state.get("error_type", "unknown"),
            research_findings="\n".join(state.get("research_findings", [])),
            code_context=code_context
        )
        
        response = self.llm.generate(
            prompt=prompt,
            system_prompt=prompts.CODE_AUDITOR_SYSTEM
        )
        
        self._log("\n[OK] Code analysis complete")
        
        return {
            "code_context": code_context + f"\n\n[Analysis]\n{response}",
            "messages": state.get("messages", []) + [f"[Code Auditor] {response}"],
            "status": "solving"
        }
    
    # =========================================================================
    # NODE 4: SOLVER
    # =========================================================================
    
    def solver(self, state: AgentState) -> Dict[str, Any]:
        """
        Synthesise all findings and propose a solution.
        
        This is the final node that combines the diagnosis, research, and
        code analysis to provide a comprehensive fix.
        """
        self._log("\n" + "="*60)
        self._log("SOLVER NODE - Proposing solution...")
        self._log("="*60)
        
        # Build comprehensive prompt
        prompt = prompts.SOLVER_PROMPT.format(
            error_summary=state.get("error_summary", ""),
            error_type=state.get("error_type", "unknown"),
            research_findings="\n".join(state.get("research_findings", [])),
            code_analysis=state.get("code_context", "No code analysis available")
        )
        
        response = self.llm.generate(
            prompt=prompt,
            system_prompt=prompts.SOLVER_SYSTEM
        )
        
        # Parse JSON response (with fallback)
        parsed = parse_json_response(response)
        
        if not parsed:
            # Fallback to legacy text parsing
            parsed = parse_llm_response(response, [
                "DIAGNOSIS_SUMMARY",
                "SOLUTION_CONFIDENCE",
                "PROPOSED_SOLUTION",
                "STEP_BY_STEP",
                "CODE_CHANGES",
                "COMMANDS_TO_RUN",
                "REQUIRES_APPROVAL",
                "APPROVAL_REASON",
                "PREVENTION",
                "VERIFICATION"
            ])
            # Parse confidence score
            try:
                confidence = float(parsed.get("solution_confidence", "0.5"))
            except ValueError:
                confidence = 0.5
            
            # Parse steps
            steps_text = parsed.get("step_by_step", "")
            steps = [s.strip() for s in re.findall(r'\d+\.\s*(.+)', steps_text)]
            
            requires_approval = parsed.get("requires_approval", "no").lower() == "yes"
            proposed_solution = parsed.get("proposed_solution", response)
            code_changes = parsed.get("code_changes", "")
            approval_reason = parsed.get("approval_reason", "")
        else:
            # JSON response - structured data
            confidence = parsed.get("confidence_score", 0.5)
            steps = parsed.get("step_by_step", [])
            requires_approval = parsed.get("requires_approval", False)
            approval_reason = parsed.get("approval_reason") or ""
            
            # Build human-readable solution from JSON
            root_cause = parsed.get("root_cause", "")
            solution_summary = parsed.get("solution_summary", "")
            commands = parsed.get("executable_commands", [])
            file_changes = parsed.get("file_changes", [])
            prevention = parsed.get("prevention", "")
            verification = parsed.get("verification", "")
            
            # Format proposed solution for display
            solution_parts = [root_cause, "", solution_summary, ""]
            
            if steps:
                solution_parts.append("Steps:")
                for i, step in enumerate(steps, 1):
                    solution_parts.append(f"  {i}. {step}")
                solution_parts.append("")
            
            if commands:
                solution_parts.append("Commands to run:")
                for cmd in commands:
                    solution_parts.append(f"  $ {cmd}")
                solution_parts.append("")
            
            if file_changes:
                solution_parts.append("File changes:")
                for fc in file_changes:
                    solution_parts.append(f"  - {fc.get('file_path', 'unknown')}: {fc.get('description', '')}")
                solution_parts.append("")
            
            if prevention:
                solution_parts.append(f"Prevention: {prevention}")
            if verification:
                solution_parts.append(f"Verification: {verification}")
            
            proposed_solution = "\n".join(solution_parts)
            
            # Format code changes
            code_changes_parts = []
            for fc in file_changes:
                if fc.get("before") and fc.get("after"):
                    code_changes_parts.append(f"File: {fc.get('file_path', 'unknown')}")
                    code_changes_parts.append(f"Before:\n{fc.get('before', '')}")
                    code_changes_parts.append(f"After:\n{fc.get('after', '')}")
                    code_changes_parts.append("---")
            code_changes = "\n".join(code_changes_parts)
        
        self._log(f"\n[OK] Solution confidence: {confidence:.0%}")
        
        # Determine final status
        if requires_approval:
            self._log(f"[WARN] This solution requires human approval")
            status = "awaiting_approval"
        elif confidence < 0.4:
            self._log(f"[WARN] Low confidence - may need more research")
            status = "complete"  # Still complete, but with low confidence warning
        else:
            status = "complete"
        
        return {
            "proposed_solution": proposed_solution,
            "solution_confidence": confidence,
            "solution_steps": steps,
            "code_changes": code_changes,
            "needs_human_approval": requires_approval,
            "pending_action": approval_reason,
            "messages": state.get("messages", []) + [f"[Solver] {response}"],
            "status": status
        }
    
    # =========================================================================
    # NODE 5: HUMAN APPROVAL (Conditional)
    # =========================================================================
    
    def human_approval(self, state: AgentState) -> Dict[str, Any]:
        """
        Wait for human approval before executing risky operations.
        
        This is a checkpoint node that pauses execution and requires
        explicit user approval to continue.
        """
        self._log("\n" + "="*60)
        self._log("HUMAN APPROVAL REQUIRED")
        self._log("="*60)
        
        self._log(f"\n[WARN] The agent wants to perform the following action:")
        self._log(f"\n{state.get('pending_action', 'No details provided')}")
        self._log(f"\nProposed solution:")
        self._log(f"{state.get('proposed_solution', 'N/A')}")
        
        return {
            "status": "awaiting_approval",
            "messages": state.get("messages", []) + ["[System] Awaiting human approval"]
        }


# =============================================================================
# ROUTING FUNCTIONS (for conditional edges)
# =============================================================================

def should_continue_research(state: AgentState) -> str:
    """
    Determine if the webscraper should loop back for more searches.
    
    Returns:
        "research" to continue searching
        "audit" to proceed to code audit
    """
    if state.get("status") == "researching":
        iterations = state.get("iterations", 0)
        max_iterations = state.get("max_iterations", 3)
        
        if iterations < max_iterations:
            return "research"
            
    return "audit"


def check_solution_confidence(state: AgentState) -> str:
    """
    Determine next step based on solution confidence.
    
    Returns:
        "refine" to go back to research
        "approve" if human approval needed
        "end" to finish
    """
    confidence = state.get("solution_confidence", 0.0)
    iterations = state.get("iterations", 0)
    max_iterations = state.get("max_iterations", 3)
    
    # If very low confidence and haven't exhausted iterations, refine
    if confidence < 0.3 and iterations < max_iterations:
        return "refine"
    
    # If approval needed
    if state.get("needs_human_approval", False):
        return "approve"
    
    return "end"
