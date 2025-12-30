# DevOps Incident Responder Agent

An autonomous, graph-based AI agent that diagnoses and resolves runtime errors like a Junior Site Reliability Engineer (SRE). Built with **LangGraph** to demonstrate controllable, state-machine architecture.

![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)
![LangGraph](https://img.shields.io/badge/LangGraph-State%20Machine-green.svg)
![Licence](https://img.shields.io/badge/Licence-MIT-yellow.svg)

## What This Project Demonstrates

This is not a "black box" AI that you just hope works. It's a **controllable, observable agent** with:

- **State Machine Architecture**: Explicit nodes and edges you can trace
- **Cyclical Graph Flows**: Self-correcting research loops when initial solutions fail
- **Human-in-the-Loop**: Approval checkpoints for risky operations
- **Tool Integration**: Web search (Tavily) + Code analysis
- **Observable State**: Full visibility into the agent's reasoning at every step

## Architecture

```
┌─────────────┐
│   INPUT     │ ← User pastes error log/stack trace
└──────┬──────┘
       │
       ▼
┌─────────────┐
│DIAGNOSTICIAN│ → Categorises error (DB? Network? Code?)
└──────┬──────┘   Generates search queries
       │
       ▼
┌─────────────┐     ┌─────────────────┐
│ RESEARCHER  │ ◄───┤ LOOP: If more   │
└──────┬──────┘     │ info needed     │
       │            └─────────────────┘
       │ Tavily Search API
       ▼
┌─────────────┐
│ CODE AUDITOR│ → Examines relevant source files
└──────┬──────┘
       │
       ▼
┌─────────────┐     ┌─────────────────┐
│   SOLVER    │ ────┤ LOOP: Back to   │
└──────┬──────┘     │ research if     │
       │            │ low confidence  │
       │            └─────────────────┘
       ▼
┌─────────────┐
│HUMAN APPROVE│ → Checkpoint for destructive commands
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   OUTPUT    │ → Solution + Steps + Code Changes
└─────────────┘
```

## Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/yourusername/devops-incident-responder.git
cd devops-incident-responder

# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure API Keys

```bash
# Copy the example env file
copy .env.example .env  # Windows
# cp .env.example .env  # Linux/Mac

# Edit .env with your API keys
```

You need:
- **Google Gemini API Key** (FREE) - for the LLM reasoning
- **Tavily API Key** (FREE) - for web search

Get a free Gemini key at: https://aistudio.google.com/app/apikey
Get a free Tavily key at: https://tavily.com

### 3. Run the Agent

```bash
# Interactive mode with sample errors
python -m src.main

# Direct error input
python -m src.main --error "psycopg2.OperationalError: could not connect to server"

# From a log file
python -m src.main --file error.log
```

## Project Structure

```
devops-incident-responder/
├── src/
│   ├── __init__.py
│   ├── main.py           # CLI entry point
│   ├── graph.py          # LangGraph workflow definition
│   ├── nodes.py          # Node functions (the workers)
│   ├── state.py          # AgentState TypedDict
│   ├── prompts.py        # All LLM prompts
│   ├── llm.py            # Multi-provider LLM interface
│   └── tools/
│       ├── __init__.py
│       ├── search_tool.py   # Tavily integration
│       └── file_tool.py     # Safe file reader
├── tests/
│   └── test_agent.py
├── .env.example
├── .gitignore
├── requirements.txt
├── pyproject.toml
└── README.md
```

## Key Features

### State Machine (Not Black Box)

```python
# Every node explicitly modifies state
class AgentState(TypedDict):
    error_log: str           # Input
    error_type: str          # Diagnosis result
    search_queries: List[str] # Generated queries
    research_findings: List[str]
    proposed_solution: str
    solution_confidence: float  # 0.0 - 1.0
    needs_human_approval: bool  # Safety checkpoint
```

### Conditional Edges (Self-Correction)

```python
def check_solution_confidence(state: AgentState) -> str:
    if state["solution_confidence"] < 0.3:
        return "refine"  # Go back to research
    if state["needs_human_approval"]:
        return "approve"  # Checkpoint
    return "end"

workflow.add_conditional_edges("solve", check_solution_confidence)
```

### Human-in-the-Loop

When the agent wants to run a destructive command:

```
HUMAN APPROVAL REQUIRED
-----------------------------
The agent wants to perform:
  DROP TABLE users; -- Recreate with correct schema

Type 'yes' to approve or 'no' to abort:
```

## Sample Errors to Test

The interactive mode includes 5 sample errors:

1. **PostgreSQL Connection Timeout** - Docker networking issue
2. **Docker OOMKilled** - Memory exhaustion
3. **Kubernetes CrashLoopBackOff** - Missing build artifact
4. **AWS Lambda Timeout** - Cold start + slow query
5. **NGINX 502 Bad Gateway** - Backend service down

## Example Output

```
INCIDENT RESPONDER AGENT STARTING
====================================

DIAGNOSTICIAN NODE - Analysing error...
[OK] Error Type: database
Summary: PostgreSQL connection failing due to Docker network configuration
Will search for: ["postgres connection refused docker-compose", ...]

RESEARCHER NODE - Searching for solutions...
Found: Docker Compose networking - Stack Overflow
Found: PostgreSQL Docker connection troubleshooting

CODE AUDITOR NODE - Examining code files...
Reading: docker-compose.yml

SOLVER NODE - Proposing solution...
====================================

INVESTIGATION SUMMARY
---------------------
Error Type: database
Solution Confidence: 85%

PROPOSED SOLUTION
-----------------
Add depends_on with healthcheck to ensure DB is ready before app starts.

STEPS TO IMPLEMENT
1. Add healthcheck to postgres service
2. Add depends_on condition to app service
3. Rebuild containers: docker-compose up --build
```

## Why This Wins Interviews

### Resume Bullet Points

> **Autonomous DevOps Agent (LangGraph, Python)**
> - Engineered a multi-step agentic workflow using **LangGraph** to autonomously diagnose and resolve runtime errors
> - Implemented **state-machine architecture** with cyclical graph flows, allowing self-correction when initial solutions fail
> - Integrated **Human-in-the-Loop** checkpoints for safe execution of automated code patches
> - Built with **tool orchestration** (Tavily Search, File Analysis) demonstrating practical AI agent patterns

### Interview Talking Points

1. **"Why LangGraph over CrewAI/AutoGen?"**
   > "CrewAI abstracts away the control flow. LangGraph forces you to explicitly define the state machine - I can show you exactly how information flows between nodes, where loops occur, and how errors are handled."

2. **"How do you handle failures?"**
   > "The graph has conditional edges. If the Solver's confidence is below 30%, it automatically routes back to the Researcher with a refined query. There's also a max_iterations guard to prevent infinite loops."

3. **"Is this safe for production?"**
   > "Yes - dangerous operations trigger a Human-in-the-Loop checkpoint. The agent pauses and waits for explicit approval before executing any destructive commands."

## Extending the Agent

### Add a New Node

```python
# In nodes.py
def log_analyser(self, state: AgentState) -> Dict[str, Any]:
    """New node that analyses log patterns."""
    # Your logic here
    return {"log_patterns": patterns}

# In graph.py
workflow.add_node("analyse_logs", factory.log_analyser)
workflow.add_edge("diagnose", "analyse_logs")
workflow.add_edge("analyse_logs", "research")
```

### Add a New Tool

```python
# In tools/kubernetes_tool.py
class KubectlTool:
    def get_pod_logs(self, pod_name: str) -> str:
        # Implementation
        pass
```

## Licence

MIT Licence - feel free to use this for your portfolio!

## Contributing

1. Fork the repository
2. Create your feature branch
3. Run tests: `pytest tests/ -v`
4. Submit a pull request

---

Built to demonstrate production-grade AI agent architecture.