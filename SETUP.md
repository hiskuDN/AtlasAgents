# AtlasAgents Setup Guide

## Installation

```bash
# Install the package in development mode
pip install -e .

# Or with dev dependencies
pip install -e ".[dev]"
```

## Required Configuration

### 1. Settings Configuration (`~/.atlas/settings.json`)

The following values need to be configured:

```json
{
  "telegram": {
    "group_id": "<YOUR_TELEGRAM_GROUP_ID>",  // Required: Telegram group ID for approvals
    "bot_token": "<YOUR_TELEGRAM_BOT_TOKEN>"  // Required: Bot token from @BotFather
  },
  "models": {
    "providers": {
      // If using OpenAI:
      "api_gpt4o": {
        "api_key": "<YOUR_OPENAI_API_KEY>"  // Optional: Only if using OpenAI
      },
      // If using Anthropic:
      "api_claude": {
        "api_key": "<YOUR_ANTHROPIC_API_KEY>"  // Optional: Only if using Anthropic
      }
    }
  }
}
```

### 2. MCP Configuration (`atlas.config.yaml`)

When you initialize a project, the following paths will be automatically updated:

```yaml
mcp:
  transports:
    - name: filesystem
      env:
        ROOT: "<AUTO_UPDATED>"  # Will be set to project workspace path

    - name: sqlite
      env:
        SQLITE_PATH: "<AUTO_UPDATED>"  # Will be set to project's atlas.db

    - name: git
      env:
        REPO_PATH: "<AUTO_UPDATED>"  # Will be set to project workspace path
```

### 3. Environment Variables (Optional)

If you prefer environment variables over config files:

```bash
# For Telegram
export ATLAS_TELEGRAM_BOT_TOKEN="your_bot_token"
export ATLAS_TELEGRAM_GROUP_ID="your_group_id"

# For AI Models (if using cloud providers)
export OPENAI_API_KEY="your_openai_key"
export ANTHROPIC_API_KEY="your_anthropic_key"
```

## Local Model Setup (Ollama)

If using local models with Ollama:

```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Pull required models
ollama pull gemma2:latest
ollama pull qwen2.5:latest

# Verify Ollama is running
curl http://localhost:11434/api/tags
```

## MCP Server Setup

Install required MCP servers:

```bash
# Filesystem server
pip install modelcontextprotocol-servers

# Git server
pip install mcp-server-git

# SQLite server (if needed)
pip install mcp-server-sqlite
```

## Telegram Bot Setup

1. Create a bot via @BotFather on Telegram
2. Get the bot token
3. Create a group and add the bot as admin
4. Get the group ID:
   ```python
   # Use this script to find your group ID
   import requests

   BOT_TOKEN = "your_bot_token"
   url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
   response = requests.get(url)
   print(response.json())  # Look for "chat": {"id": -1234567890}
   ```

## Quick Start

```bash
# 1. Configure settings
cp templates/settings.json ~/.atlas/settings.json
# Edit ~/.atlas/settings.json with your values

# 2. Initialize a project
atlas init myproject

# 3. Switch to project
atlas switch myproject

# 4. Check status
atlas status

# 5. Start the orchestrator
atlas run plan
```

## Verification Checklist

- [ ] Ollama is running (`curl http://localhost:11434`)
- [ ] Required models are pulled (`ollama list`)
- [ ] Telegram bot token is configured
- [ ] Telegram group ID is configured
- [ ] MCP servers are installed
- [ ] Python 3.10+ is installed
- [ ] All pip dependencies are installed

## Troubleshooting

### Ollama Connection Error
```bash
# Start Ollama service
ollama serve
```

### Telegram Bot Not Responding
- Ensure bot is added to group as admin
- Check bot token is correct
- Verify group ID is negative (groups have negative IDs)

### MCP Server Errors
- Ensure uvx is installed: `pip install uvx`
- Check MCP servers are installed correctly
- Verify paths in atlas.config.yaml are absolute paths