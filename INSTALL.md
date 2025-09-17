# Installation Guide

## Quick Install (Development Mode)

1. **Create and activate a virtual environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Install atlas in development mode:**
   ```bash
   ./install_dev.sh
   ```

4. **Verify installation:**
   ```bash
   atlas --help
   ```

## Manual Installation

If the install script doesn't work, you can manually set up the development environment:

1. **Activate virtual environment:**
   ```bash
   source venv/bin/activate
   ```

2. **Install all dependencies:**
   ```bash
   pip install click pydantic pydantic-settings mcp httpx python-telegram-bot \
              ollama openai anthropic pyyaml rich python-dotenv GitPython \
              aiofiles jinja2 structlog
   ```

3. **Add project to Python path:**
   ```bash
   export PYTHONPATH="${PYTHONPATH}:$(pwd)"
   ```

4. **Run directly with Python:**
   ```bash
   python -m orchestrator.cli --help
   ```

## Known Issues

### Python 3.13 Compatibility
There's a known issue with `pip install -e .` on Python 3.13 related to the setuptools build backend. The `install_dev.sh` script provides a workaround by directly setting up the Python path and creating the atlas command.

### Alternative: Use Python 3.12 or 3.11
If you encounter issues with Python 3.13, consider using Python 3.12 or 3.11:
```bash
# Using pyenv
pyenv install 3.12.7
pyenv local 3.12.7
python -m venv venv
source venv/bin/activate
pip install -e .
```

## Next Steps

After installation, you can:

1. Initialize a new project:
   ```bash
   atlas init myproject
   ```

2. Check project status:
   ```bash
   atlas status
   ```

3. Run smoke tests:
   ```bash
   atlas mcp tools
   atlas mcp test filesystem.read --args '{"path": "README.md"}'
   ```