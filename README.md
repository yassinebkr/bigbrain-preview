# BigBrain Preview - Multi-Brain AI Agent System

A modular, async AI agent system demonstrating the 3-layer BigBrain architecture with message bus communication.

## Architecture

**BigBrain implements a 3-layer architecture:**

1. **Front Brain** - User-facing intelligence layer
   - Natural conversation and intent understanding
   - Focus management and attention filtering  
   - Context preservation across sessions

2. **Orchestrator** - Task decomposition and routing layer
   - Breaks down complex tasks into subtasks
   - Manages dependencies between subtasks (ReWOO pattern)
   - Routes work to appropriate execution brains

3. **Execution Brains** - Specialized worker brains
   - PythonBrain: Code execution with subprocess isolation
   - ResearchBrain: Web search and information gathering
   - Extensible design for additional brain types

**Message Bus Communication:**
- CAN bus-style decoupled communication
- Full message logging and replay capability
- Priority-based filtering for focus management
- Broadcast and point-to-point messaging

## Features

- ✅ **Cross-platform Python execution** with subprocess isolation
- ✅ **Rich terminal UI** with live status updates
- ✅ **Event-driven architecture** - non-blocking message handling
- ✅ **Task decomposition** with dependency tracking
- ✅ **Memory system** - working, project, and long-term memory
- ✅ **Focus management** - intelligent attention filtering
- ✅ **Comprehensive logging** - full audit trail of all messages

## Installation

```bash
# Clone or navigate to the project directory
cd bigbrain_preview

# Install dependencies
pip install pydantic rich pytest pytest-asyncio

# Run BigBrain
python3 -m bigbrain
```

## Usage

### Interactive Mode
```bash
python3 -m bigbrain --mode interactive
```

### Demo Mode (Default)
```bash
python3 -m bigbrain --mode demo
```

### Command Line Options
```bash
python3 -m bigbrain --help

Options:
  --workspace WORKSPACE  Workspace name (default: demo)
  --mode {interactive,demo}  Run mode (default: demo)  
  --log-dir LOG_DIR     Log directory (default: logs)
```

## Example Tasks

Once running, you can interact with BigBrain naturally:

```
BigBrain: Write a Python script to calculate fibonacci numbers

BigBrain: Create a file with today's date and read it back

BigBrain: help

BigBrain: status
```

The system will automatically:
1. Parse your intent through the Front Brain
2. Route tasks to the appropriate Orchestrator
3. Break complex tasks into subtasks
4. Execute code via the Python Brain
5. Show results in the Rich UI

## Architecture Benefits

**Modularity**: Each brain is independent and can be developed/deployed separately

**Scalability**: Easy to add new brain types or run brains on different machines

**Observability**: Full message bus logging provides complete system visibility

**Resilience**: Failure in one brain doesn't affect others

**Focus Management**: Intelligent filtering prevents information overload

## Development

### Running Tests
```bash
python3 -m pytest tests/ -v
```

### File Structure
```
bigbrain/
├── __init__.py          # Main exports
├── __main__.py          # Entry point
├── bus/                 # Message bus system
├── orchestrator/        # Task routing and management
├── brains/             # Execution worker brains
├── front/              # User-facing intelligence
├── ui/                 # User interface adapters
├── memory/             # Memory management system
├── verification/       # Code verification pipeline
└── tests/              # Test suite
```

## Status

🚧 **This is a preview/reference implementation** designed to demonstrate the BigBrain architecture concepts. 

**What works:**
- Complete message bus communication system
- Python code execution with subprocess isolation  
- Rich terminal UI with live updates
- Task orchestration with dependency tracking
- Comprehensive test suite

**Production considerations:**
- Add proper sandboxing (Docker, bubblewrap) for code execution
- Implement LLM integration for natural language processing
- Add authentication and multi-user support
- Scale message bus for distributed deployment
- Add persistent storage for memory systems

## License

This is a reference implementation for educational and demonstration purposes.