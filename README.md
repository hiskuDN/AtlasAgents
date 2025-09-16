# AtlasAgents

Local-first multi-agent coding system with Model Context Protocol (MCP) integration.

## Architecture

AtlasAgents is a sophisticated orchestration system that manages AI coding agents through a controlled pipeline with human approval gates via Telegram. The system uses MCP for tool access and maintains strict workspace isolation.

### Key Features

- **Multi-Agent Pipeline**: Planner → Spec-Writer → Coder → Reviewer workflow
- **MCP Integration**: Filesystem, Database, Git operations via Model Context Protocol
- **Human-in-the-Loop**: Telegram-based approval system for all mutations
- **Local-First**: All operations run locally with optional cloud model support
- **Git-Based Safety**: Shadow checkpoints and branch-based development
- **Workspace Isolation**: Each project runs in isolated workspace with root confinement

## Installation

```bash
# Install in development mode
pip install -e .

# Install with dev dependencies
pip install -e ".[dev]"
```

## Quick Start

```bash
# Initialize a new project
atlas init myproject

# Switch to project
atlas switch myproject

# Check status
atlas status

# Run planning stage
atlas run plan
```

## Project Structure

```
/atlas/
  orchestrator/         # Core orchestration system
    core/              # State machine and orchestrator
    agents/            # Agent implementations
    mcp/               # MCP client and tool registry
    telegram/          # Telegram bot integration
    models/            # Database models
    utils/             # Utilities
  templates/           # Project templates
  workspaces/          # Project workspaces
  ~/.atlas/            # Global configuration
    settings.json      # Settings and model config
    history/           # Git checkpoints
```

## Configuration

Settings are stored in `~/.atlas/settings.json`. See `tasks.md` for detailed configuration options.

## Development

```bash
# Run tests
pytest

# Format code
black orchestrator/
ruff check orchestrator/

# Type checking
mypy orchestrator/
```

## License

MIT