#!/bin/bash

# Activate virtual environment
source ./venv/bin/activate

# Add the project root to PYTHONPATH for development
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

# Create a .pth file in site-packages to add our project to the path
SITE_PACKAGES=$(python -c "import site; print(site.getsitepackages()[0])")
echo "$(pwd)" > "${SITE_PACKAGES}/atlas-agents.pth"

# Create the atlas command script
cat > ./venv/bin/atlas << 'EOF'
#!/Users/hisku/Documents/Workspace/Personal/AtlasAgents/venv/bin/python
# -*- coding: utf-8 -*-
import sys
import os
sys.path.insert(0, '/Users/hisku/Documents/Workspace/Personal/AtlasAgents')
from orchestrator.cli import main

if __name__ == '__main__':
    sys.exit(main())
EOF

# Make the atlas command executable
chmod +x ./venv/bin/atlas

echo "✅ Installation complete!"
echo ""
echo "To use atlas, make sure your virtual environment is activated:"
echo "  source ./venv/bin/activate"
echo ""
echo "Then you can run:"
echo "  atlas --help"