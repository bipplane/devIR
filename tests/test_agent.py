"""
Tests for the DevOps Incident Responder Agent

Run with: pytest tests/ -v

Test Coverage:
- State management and initialisation
- JSON parsing resilience (LLM drift handling)
- Legacy text parsing (fallback)
- Node logic with mocked LLM calls
- Security: path traversal and file access controls
"""

import pytest
from unittest.mock import MagicMock, patch
from src.state import AgentState, create_initial_state
from src.nodes import parse_llm_response, parse_json_response


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


class TestJSONParsing:
    """Tests for JSON response parsing."""
    
    def test_parse_clean_json(self):
        """Test parsing a clean JSON response."""
        response = '{"error_type": "database", "severity": "high"}'
        parsed = parse_json_response(response)
        
        assert parsed["error_type"] == "database"
        assert parsed["severity"] == "high"
    
    def test_parse_json_with_thinking_tags(self):
        """Test parsing JSON with <thinking> tags."""
        response = """<thinking>
Let me analyse this error...
It looks like a database connection issue.
</thinking>

{"error_type": "database", "severity": "high", "error_summary": "Connection failed"}"""
        parsed = parse_json_response(response)
        
        assert parsed["error_type"] == "database"
        assert parsed["severity"] == "high"
        assert parsed["error_summary"] == "Connection failed"
    
    def test_parse_json_with_markdown_blocks(self):
        """Test parsing JSON wrapped in markdown code blocks."""
        response = """Here is the analysis:

```json
{"error_type": "network", "confidence": 0.85}
```

Let me know if you need more details."""
        parsed = parse_json_response(response)
        
        assert parsed["error_type"] == "network"
        assert parsed["confidence"] == 0.85
    
    def test_parse_json_with_nested_objects(self):
        """Test parsing JSON with nested objects and arrays."""
        response = """{
    "error_type": "configuration",
    "search_keywords": ["docker config", "env vars"],
    "relevant_solutions": [
        {"source_url": "https://example.com", "confidence": "high"}
    ]
}"""
        parsed = parse_json_response(response)
        
        assert parsed["error_type"] == "configuration"
        assert len(parsed["search_keywords"]) == 2
        assert parsed["relevant_solutions"][0]["confidence"] == "high"
    
    def test_parse_invalid_json_returns_empty(self):
        """Test that invalid JSON returns an empty dict."""
        response = "This is not valid JSON at all"
        parsed = parse_json_response(response)
        
        assert parsed == {}


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
    """Tests for tool safety features (DevSecOps)."""
    
    def test_file_tool_blocks_env_files(self):
        """Test that .env files are blocked - prevents credential leakage."""
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
    
    def test_file_tool_blocks_path_traversal(self):
        """Test that path traversal attacks are blocked."""
        from src.tools.file_tool import FileReaderTool
        
        tool = FileReaderTool(base_directory="/app")
        
        from pathlib import Path
        # Attempts to escape the base directory
        assert not tool._is_safe_path(Path("../../../etc/passwd"))
        assert not tool._is_safe_path(Path("/etc/passwd"))


class TestNodesMocked:
    """
    Test actual node functions with mocked LLM.
    
    This proves the node logic works without making API calls.
    Essential for CI/CD pipelines and cost control.
    """
    
    def test_diagnostician_parses_json_response(self):
        """Test diagnostician node correctly parses LLM JSON output."""
        from src.nodes import NodeFactory
        
        # Create a mock LLM
        mock_llm = MagicMock()
        mock_llm.generate.return_value = '''{
            "error_type": "database",
            "severity": "high",
            "error_summary": "PostgreSQL connection refused",
            "affected_components": ["database", "api"],
            "search_keywords": ["postgres connection refused docker"],
            "files_to_check": ["docker-compose.yml"],
            "immediate_actions": ["Check if database container is running"]
        }'''
        
        # Create factory with mocked dependencies
        factory = NodeFactory(
            llm=mock_llm,
            search_tool=MagicMock(),
            file_tool=MagicMock(),
            verbose=False
        )
        
        # Create test state
        state = create_initial_state("psycopg2.OperationalError: connection refused")
        
        # Run the node
        result = factory.diagnostician(state)
        
        # Verify results
        assert result["error_type"] == "database"
        assert result["error_summary"] == "PostgreSQL connection refused"
        assert "database" in result["affected_components"]
        assert len(result["search_queries"]) > 0
        assert result["status"] == "researching"
        
        # Verify the error log was passed to the LLM
        call_args = mock_llm.generate.call_args
        assert "connection refused" in call_args.kwargs.get("prompt", "")
    
    def test_diagnostician_handles_malformed_json(self):
        """Test diagnostician gracefully handles malformed LLM output."""
        from src.nodes import NodeFactory
        
        # LLM returns garbage
        mock_llm = MagicMock()
        mock_llm.generate.return_value = "ERROR_TYPE: database\nERROR_SUMMARY: Connection failed"
        
        factory = NodeFactory(
            llm=mock_llm,
            search_tool=MagicMock(),
            file_tool=MagicMock(),
            verbose=False
        )
        
        state = create_initial_state("Some error")
        result = factory.diagnostician(state)
        
        # Should fall back to legacy parsing
        assert result["error_type"] == "database"
        assert "Connection failed" in result["error_summary"]
    
    def test_solver_extracts_confidence_score(self):
        """Test solver correctly extracts confidence from JSON."""
        from src.nodes import NodeFactory
        
        mock_llm = MagicMock()
        mock_llm.generate.return_value = '''{
            "root_cause": "Database container not running",
            "confidence_score": 0.85,
            "solution_summary": "Start the database container",
            "step_by_step": ["Run docker-compose up -d db"],
            "executable_commands": ["docker-compose up -d db"],
            "file_changes": [],
            "requires_approval": false,
            "rollback_steps": ["docker-compose down"],
            "prevention": "Add health checks",
            "verification": "Check logs"
        }'''
        
        factory = NodeFactory(
            llm=mock_llm,
            search_tool=MagicMock(),
            file_tool=MagicMock(),
            verbose=False
        )
        
        state = create_initial_state("error")
        state["error_summary"] = "Connection refused"
        state["error_type"] = "database"
        state["research_findings"] = ["Use docker-compose"]
        state["code_context"] = "No code"
        
        result = factory.solver(state)
        
        assert result["solution_confidence"] == 0.85
        assert result["status"] == "complete"
        assert not result["needs_human_approval"]
    
    def test_solver_flags_dangerous_operations(self):
        """Test solver correctly flags operations needing approval."""
        from src.nodes import NodeFactory
        
        mock_llm = MagicMock()
        mock_llm.generate.return_value = '''{
            "root_cause": "Corrupted database",
            "confidence_score": 0.9,
            "solution_summary": "Drop and recreate the table",
            "step_by_step": ["Backup data", "Drop table", "Recreate"],
            "executable_commands": ["DROP TABLE users;"],
            "file_changes": [],
            "requires_approval": true,
            "approval_reason": "Destructive database operation",
            "rollback_steps": ["Restore from backup"],
            "prevention": "Add migrations",
            "verification": "Query the table"
        }'''
        
        factory = NodeFactory(
            llm=mock_llm,
            search_tool=MagicMock(),
            file_tool=MagicMock(),
            verbose=False
        )
        
        state = create_initial_state("error")
        state["error_summary"] = "Table corrupted"
        state["error_type"] = "database"
        state["research_findings"] = []
        state["code_context"] = ""
        
        result = factory.solver(state)
        
        assert result["needs_human_approval"] == True
        assert result["status"] == "awaiting_approval"
        assert "Destructive" in result["pending_action"]


class TestStreaming:
    """Tests for streaming LLM output."""
    
    def test_llm_has_generate_stream_method(self):
        """Test that LLM class has streaming capability."""
        from src.llm import GeminiLLM
        
        llm = GeminiLLM(api_key="test_key")
        assert hasattr(llm, 'generate_stream')
        assert callable(llm.generate_stream)
    
    def test_base_llm_requires_stream_method(self):
        """Test that BaseLLM abstract class requires generate_stream."""
        from src.llm import BaseLLM
        import inspect
        
        # Check that generate_stream is an abstract method
        assert 'generate_stream' in BaseLLM.__abstractmethods__
    
    def test_generate_solution_explanation_yields_chunks(self):
        """Test that the generator actually yields data chunk by chunk."""
        from src.graph import IncidentResponder
        from src.llm import GeminiLLM
        
        # Setup mock LLM
        mock_llm = MagicMock(spec=GeminiLLM)
        fake_stream = iter(["Checking ", "database ", "connection..."])
        mock_llm.generate_stream.return_value = fake_stream
        
        # Create responder and inject mock
        with patch('src.graph.get_llm', return_value=mock_llm):
            with patch('src.graph.TavilySearchTool'):
                with patch('src.graph.FileReaderTool'):
                    responder = IncidentResponder(verbose=False)
                    responder.llm = mock_llm
        
        # Create minimal state
        state = create_initial_state("test error")
        state["error_type"] = "database"
        state["error_summary"] = "Connection failed"
        state["proposed_solution"] = "Restart database"
        state["solution_steps"] = ["Step 1", "Step 2"]
        
        # Call the generator and collect results
        generator = responder.generate_solution_explanation(state)
        results = list(generator)
        
        # Assert chunks were yielded correctly
        assert results == ["Checking ", "database ", "connection..."]
        assert len(results) == 3
        
        # Verify LLM was called with correct error context
        call_args = mock_llm.generate_stream.call_args
        prompt = call_args[0][0]
        assert "database" in prompt
        assert "Connection failed" in prompt
    
    def test_generate_solution_explanation_is_generator(self):
        """Test that the method returns a generator, not a list."""
        from src.graph import IncidentResponder
        from src.llm import GeminiLLM
        import types
        
        mock_llm = MagicMock(spec=GeminiLLM)
        mock_llm.generate_stream.return_value = iter(["chunk"])
        
        with patch('src.graph.get_llm', return_value=mock_llm):
            with patch('src.graph.TavilySearchTool'):
                with patch('src.graph.FileReaderTool'):
                    responder = IncidentResponder(verbose=False)
                    responder.llm = mock_llm
        
        state = create_initial_state("error")
        state["error_type"] = "test"
        
        result = responder.generate_solution_explanation(state)
        
        # Should be a generator, not a list
        assert isinstance(result, types.GeneratorType)


# Integration test (requires API keys)
@pytest.mark.skipif(True, reason="Requires API keys - run manually with: pytest tests/ -v -k Integration")
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
