"""
Tests for the DevOps Incident Responder Agent

Run with: pytest tests/ -v
"""

import pytest
from src.state import AgentState, create_initial_state
from src.nodes import parse_llm_response


class TestAgentState:
    """Tests for the AgentState and state creation."""
    
    def test_create_initial_state(self):
        """Test that initial state is created with correct defaults."""
        error = "Test error message"
        state = create_initial_state(error)
        
        assert state["error_log"] == error
        assert state["error_type"] == "unknown"
        assert state["iterations"] == 0
        assert state["max_iterations"] == 3
        assert state["status"] == "investigating"
        assert state["needs_human_approval"] == False
        
    def test_create_initial_state_custom_iterations(self):
        """Test custom max_iterations setting."""
        state = create_initial_state("error", max_iterations=5)
        assert state["max_iterations"] == 5


class TestLLMResponseParsing:
    """Tests for parsing structured LLM responses."""
    
    def test_parse_simple_response(self):
        """Test parsing a simple key-value response."""
        response = """
ERROR_TYPE: database
ERROR_SUMMARY: Connection failed
SEVERITY: high
"""
        parsed = parse_llm_response(response, ["ERROR_TYPE", "ERROR_SUMMARY", "SEVERITY"])
        
        assert parsed["error_type"] == "database"
        assert parsed["error_summary"] == "Connection failed"
        assert parsed["severity"] == "high"
        
    def test_parse_multiline_value(self):
        """Test parsing values that span multiple lines."""
        response = """
ERROR_TYPE: network
ERROR_SUMMARY: The connection to the database server timed out.
This is likely due to network configuration issues
in the Docker environment.
SEVERITY: medium
"""
        parsed = parse_llm_response(response, ["ERROR_TYPE", "ERROR_SUMMARY", "SEVERITY"])
        
        assert parsed["error_type"] == "network"
        assert "timed out" in parsed["error_summary"]
        assert "Docker environment" in parsed["error_summary"]
        
    def test_parse_missing_field(self):
        """Test that missing fields return empty string."""
        response = "ERROR_TYPE: database"
        parsed = parse_llm_response(response, ["ERROR_TYPE", "MISSING_FIELD"])
        
        assert parsed["error_type"] == "database"
        assert parsed["missing_field"] == ""
        
    def test_parse_list_format(self):
        """Test parsing bracketed list values."""
        response = "COMPONENTS: [database, redis, nginx]"
        parsed = parse_llm_response(response, ["COMPONENTS"])
        
        # Should strip brackets
        assert parsed["components"] == "database, redis, nginx"


class TestNodeLogic:
    """Tests for node decision logic."""
    
    def test_confidence_routing_low(self):
        """Test that low confidence routes to refinement."""
        from src.nodes import check_solution_confidence
        
        state = create_initial_state("error")
        state["solution_confidence"] = 0.2
        state["iterations"] = 1
        
        result = check_solution_confidence(state)
        assert result == "refine"
        
    def test_confidence_routing_high(self):
        """Test that high confidence routes to end."""
        from src.nodes import check_solution_confidence
        
        state = create_initial_state("error")
        state["solution_confidence"] = 0.8
        state["needs_human_approval"] = False
        
        result = check_solution_confidence(state)
        assert result == "end"
        
    def test_confidence_routing_approval(self):
        """Test that approval flag routes to approval node."""
        from src.nodes import check_solution_confidence
        
        state = create_initial_state("error")
        state["solution_confidence"] = 0.9
        state["needs_human_approval"] = True
        
        result = check_solution_confidence(state)
        assert result == "approve"
        
    def test_research_continues_when_needed(self):
        """Test research loop logic."""
        from src.nodes import should_continue_research
        
        state = create_initial_state("error")
        state["status"] = "researching"
        state["iterations"] = 1
        
        result = should_continue_research(state)
        assert result == "research"
        
    def test_research_stops_at_max(self):
        """Test research loop stops at max iterations."""
        from src.nodes import should_continue_research
        
        state = create_initial_state("error", max_iterations=3)
        state["status"] = "researching"
        state["iterations"] = 3  # At max
        
        result = should_continue_research(state)
        assert result == "audit"


class TestToolSafety:
    """Tests for tool safety features."""
    
    def test_file_tool_blocks_env_files(self):
        """Test that .env files are blocked."""
        from src.tools.file_tool import FileReaderTool
        
        tool = FileReaderTool(base_directory=".")
        
        # Should not be safe
        from pathlib import Path
        assert not tool._is_safe_path(Path(".env"))
        assert not tool._is_safe_path(Path("config/.env.local"))
        
    def test_file_tool_blocks_secrets(self):
        """Test that secret files are blocked."""
        from src.tools.file_tool import FileReaderTool
        
        tool = FileReaderTool(base_directory=".")
        
        from pathlib import Path
        assert not tool._is_safe_path(Path("secrets/api_key.txt"))
        assert not tool._is_safe_path(Path("credentials.json"))
        
    def test_file_tool_allows_code_files(self):
        """Test that code files are allowed."""
        from src.tools.file_tool import FileReaderTool
        
        tool = FileReaderTool(base_directory=".")
        
        # Extension should be allowed
        assert ".py" in tool.ALLOWED_EXTENSIONS
        assert ".js" in tool.ALLOWED_EXTENSIONS
        assert ".yml" in tool.ALLOWED_EXTENSIONS


# Integration test (requires API keys)
@pytest.mark.skipif(True, reason="Requires API keys")
class TestIntegration:
    """Integration tests that require real API calls."""
    
    def test_full_workflow(self):
        """Test complete agent workflow."""
        from src.graph import IncidentResponder
        
        responder = IncidentResponder(verbose=False)
        result = responder.investigate(
            "psycopg2.OperationalError: connection refused",
            max_iterations=1
        )
        
        assert result["status"] in ["complete", "awaiting_approval"]
        assert result["error_type"] != "unknown"
        assert len(result["proposed_solution"]) > 0
