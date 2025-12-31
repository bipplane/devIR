"""
DevOps Incident Responder - Main Entry Point

A LangGraph-based autonomous agent for diagnosing and resolving runtime errors.

Usage:
    # Interactive mode
    python -m src.main
    
    # Direct error input
    python -m src.main --error "ConnectionRefusedError: Could not connect to PostgreSQL"
    
    # From file
    python -m src.main --file error_log.txt
    
    # With specific LLM provider
    python -m src.main --provider gemini --error "..."
"""

import argparse
import sys
import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.graph import IncidentResponder
from src.state import AgentState


def print_banner():
    """Print the application banner."""
    banner = """
+======================================================================+
|                                                                      |
|         DEVOPS INCIDENT RESPONDER AGENT                              |
|                                                                      |
|         Autonomous Error Diagnosis & Resolution                      |
|         Built with LangGraph | State Machine Architecture            |
|                                                                      |
+======================================================================+
    """
    print(banner)


def get_sample_errors():
    """Return sample errors for demonstration."""
    return {
        "1": {
            "name": "PostgreSQL Connection Timeout",
            "error": """
Traceback (most recent call last):
  File "/app/database/connection.py", line 45, in connect
    self.conn = psycopg2.connect(**self.config)
  File "/usr/local/lib/python3.9/site-packages/psycopg2/__init__.py", line 122, in connect
    conn = _connect(dsn, connection_factory=connection_factory, **kwasync)
psycopg2.OperationalError: could not connect to server: Connection timed out
    Is the server running on host "db" (172.18.0.2) and accepting
    TCP/IP connections on port 5432?

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "/app/main.py", line 23, in <module>
    db = Database()
  File "/app/database/connection.py", line 48, in connect
    raise DatabaseConnectionError(f"Failed to connect after {self.retries} retries")
app.exceptions.DatabaseConnectionError: Failed to connect after 3 retries
"""
        },
        "2": {
            "name": "Docker Container OOMKilled",
            "error": """
$ docker logs my-app-container
[2024-01-15T10:23:45.123Z] Starting application...
[2024-01-15T10:23:46.456Z] Loading model into memory...
[2024-01-15T10:24:12.789Z] Killed

$ docker inspect my-app-container --format='{{.State.OOMKilled}}'
true

$ docker stats my-app-container --no-stream
CONTAINER ID   NAME              CPU %   MEM USAGE / LIMIT     MEM %
a1b2c3d4e5f6   my-app-container  0.00%   2.048GiB / 2GiB      100.00%
"""
        },
        "3": {
            "name": "Kubernetes Pod CrashLoopBackOff",
            "error": """
$ kubectl get pods
NAME                          READY   STATUS             RESTARTS   AGE
api-server-7d9f8c6b5-xj2m1    0/1     CrashLoopBackOff   5          10m

$ kubectl describe pod api-server-7d9f8c6b5-xj2m1
...
Events:
  Type     Reason     Age                   From               Message
  ----     ------     ----                  ----               -------
  Normal   Scheduled  10m                   default-scheduler  Successfully assigned default/api-server-7d9f8c6b5-xj2m1 to node-1
  Normal   Pulled     9m (x4 over 10m)      kubelet            Container image "myregistry/api:latest" already present on machine
  Normal   Created    9m (x4 over 10m)      kubelet            Created container api
  Normal   Started    9m (x4 over 10m)      kubelet            Started container api
  Warning  BackOff    2m (x24 over 9m)      kubelet            Back-off restarting failed container

$ kubectl logs api-server-7d9f8c6b5-xj2m1
Error: Cannot find module '/app/dist/server.js'
    at Function.Module._resolveFilename (internal/modules/cjs/loader.js:902:15)
    at Function.Module._load (internal/modules/cjs/loader.js:746:27)
"""
        },
        "4": {
            "name": "AWS Lambda Timeout",
            "error": """
{
    "errorMessage": "2024-01-15T14:30:45.123Z 8f2b4a1c-1234-5678-9abc-def012345678 Task timed out after 30.00 seconds",
    "errorType": "Runtime.ExitError"
}

CloudWatch Logs:
START RequestId: 8f2b4a1c-1234-5678-9abc-def012345678 Version: $LATEST
2024-01-15T14:30:15.123Z	8f2b4a1c-1234-5678-9abc-def012345678	INFO	Processing request...
2024-01-15T14:30:16.456Z	8f2b4a1c-1234-5678-9abc-def012345678	INFO	Connecting to RDS...
2024-01-15T14:30:17.789Z	8f2b4a1c-1234-5678-9abc-def012345678	INFO	Connection established
2024-01-15T14:30:18.012Z	8f2b4a1c-1234-5678-9abc-def012345678	INFO	Running query...
END RequestId: 8f2b4a1c-1234-5678-9abc-def012345678
REPORT RequestId: 8f2b4a1c-1234-5678-9abc-def012345678	Duration: 30003.45 ms	Billed Duration: 30000 ms	Memory Size: 512 MB	Max Memory Used: 256 MB
"""
        },
        "5": {
            "name": "NGINX 502 Bad Gateway",
            "error": """
=== NGINX Error Log ===
2024/01/15 10:30:45 [error] 12345#12345: *67890 connect() failed (111: Connection refused) 
  while connecting to upstream, client: 192.168.1.100, server: api.example.com, 
  request: "POST /api/v1/users HTTP/1.1", upstream: "http://127.0.0.1:8000/api/v1/users", 
  host: "api.example.com"

2024/01/15 10:30:46 [error] 12345#12345: *67891 no live upstreams while connecting to upstream,
  client: 192.168.1.101, server: api.example.com, request: "GET /api/v1/health HTTP/1.1", 
  upstream: "http://backend/api/v1/health", host: "api.example.com"

=== Application Status ===
$ systemctl status app-backend
● app-backend.service - Backend API Service
   Loaded: loaded (/etc/systemd/system/app-backend.service; enabled)
   Active: failed (Result: exit-code) since Mon 2024-01-15 10:30:00 UTC; 45s ago
  Process: 12345 ExecStart=/usr/bin/python3 /app/main.py (code=exited, status=1/FAILURE)
"""
        }
    }


def interactive_mode(responder: IncidentResponder):
    """Run the agent in interactive mode."""
    print_banner()
    
    samples = get_sample_errors()
    
    # Flush stdin to clear any buffered input (for Docker/PTY)
    try:
        import select
        if sys.platform != 'win32':
            while select.select([sys.stdin], [], [], 0)[0]:
                sys.stdin.read(1)
    except Exception:
        pass
    
    # Loop until valid choice is made
    while True:
        print("Choose an option:")
        print("  [1-5] Use a sample error")
        print("  [C]   Enter custom error")
        print("  [Q]   Quit")
        
        print("\nSample Errors:")
        for key, sample in samples.items():
            print(f"  {key}. {sample['name']}")
        
        print()
        sys.stdout.flush()
        
        try:
            choice = input("Enter your choice: ").strip().upper()
        except EOFError:
            print("\nNo input received. Exiting.")
            return
        
        if choice == "":
            print("\nNo input received. Please enter a valid choice.\n")
            continue
        
        if choice == "Q":
            print("Goodbye!")
            return
        
        if choice == "C":
            print("\nPaste your error (enter a blank line when done):")
            lines = []
            while True:
                try:
                    line = input()
                    if line == "":
                        break
                    lines.append(line)
                except EOFError:
                    break
            error_log = "\n".join(lines)
            break
        elif choice in samples:
            error_log = samples[choice]["error"]
            print(f"\nUsing sample: {samples[choice]['name']}")
            break
        else:
            print(f"\nInvalid choice '{choice}'. Please select 1-5, C, or Q.\n")
            continue
    
    if not error_log.strip():
        print("No error provided. Exiting.")
        return
    
    # Run the investigation
    try:
        result = responder.investigate(error_log)
        
        # Offer to stream a detailed explanation
        explain = input("\nStream detailed explanation? (y/n): ").strip().lower()
        if explain == "y":
            print("\n" + "="*60)
            print("SOLUTION EXPLANATION")
            print("="*60 + "\n")
            
            # Presentation layer: print chunks as they arrive
            for chunk in responder.generate_solution_explanation(result):
                print(chunk, end="", flush=True)
            print("\n")
        
        # Ask if user wants to save the report
        save = input("\nSave report to file? (y/n): ").strip().lower()
        if save == "y":
            save_report(result)
            
    except KeyboardInterrupt:
        print("\n\nInvestigation cancelled by user.")
        return
    except Exception as e:
        print(f"\nError during investigation: {e}")
        print("Please check your API keys and internet connection.")
        return  # Return to menu safely instead of crashing


def save_report(state: AgentState, filename: Optional[str] = None):
    """Save the investigation report to a file."""
    if filename is None:
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"incident_report_{timestamp}.md"
    
    report = f"""# Incident Investigation Report

## Error Summary
**Type:** {state.get('error_type', 'unknown')}
**Confidence:** {state.get('solution_confidence', 0):.0%}
**Iterations:** {state.get('iterations', 0)}

## Original Error
```
{state.get('error_log', 'N/A')}
```

## Diagnosis
{state.get('error_summary', 'N/A')}

## Affected Components
{', '.join(state.get('affected_components', ['N/A']))}

## Proposed Solution
{state.get('proposed_solution', 'N/A')}

## Implementation Steps
"""
    
    for i, step in enumerate(state.get('solution_steps', []), 1):
        report += f"{i}. {step}\n"
    
    if state.get('code_changes'):
        report += f"""
## Code Changes
```
{state.get('code_changes')}
```
"""
    
    if state.get('needs_human_approval'):
        report += f"""
## Requires Human Approval
{state.get('pending_action', 'No details provided')}
"""
    
    with open(filename, 'w') as f:
        f.write(report)
    
    print(f"Report saved to: {filename}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="DevOps Incident Responder - Autonomous Error Diagnosis Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.main                           # Interactive mode
  python -m src.main --error "Error message"   # Direct input
  python -m src.main --file error.log          # From file
  python -m src.main --provider gemini         # Use Gemini LLM
        """
    )
    
    parser.add_argument(
        "--error", "-e",
        type=str,
        help="Error message or stack trace to investigate"
    )
    
    parser.add_argument(
        "--file", "-f",
        type=str,
        help="File containing the error log"
    )
    
    parser.add_argument(
        "--provider", "-p",
        type=str,
        choices=["gemini"],
        default="gemini",
        help="LLM provider to use (default: gemini)"
    )
    
    parser.add_argument(
        "--model", "-m",
        type=str,
        help="Specific model to use (uses provider default if not specified)"
    )
    
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=3,
        help="Maximum research iterations (default: 3)"
    )
    
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Reduce output verbosity"
    )
    
    parser.add_argument(
        "--output", "-o",
        type=str,
        help="Save report to specified file"
    )
    
    args = parser.parse_args()
    
    # Check for required API keys
    required_keys = {
        "gemini": "GOOGLE_API_KEY"
    }
    
    llm_key = required_keys.get(args.provider)
    if llm_key and not os.getenv(llm_key):
        print(f"Warning: {llm_key} not found in environment variables")
        print(f"   Set it with: set {llm_key}=your-api-key")
    
    if not os.getenv("TAVILY_API_KEY"):
        print("Warning: TAVILY_API_KEY not found in environment variables")
        print("   Web search will not work. Get a free key at https://tavily.com")
    
    # Initialise the responder
    responder = IncidentResponder(
        llm_provider=args.provider,
        llm_model=args.model,
        verbose=not args.quiet
    )
    
    # Determine input source
    error_log = None
    
    if args.file:
        try:
            with open(args.file, 'r') as f:
                error_log = f.read()
            print(f"Loaded error from: {args.file}")
        except Exception as e:
            print(f"Could not read file: {e}")
            sys.exit(1)
    
    elif args.error:
        error_log = args.error
    
    # Run investigation or interactive mode
    if error_log:
        result = responder.investigate(error_log, max_iterations=args.max_iterations)
        
        if args.output:
            save_report(result, args.output)
    else:
        interactive_mode(responder)


if __name__ == "__main__":
    main()
