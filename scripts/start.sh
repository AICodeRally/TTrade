#!/bin/bash
# Start TTrade engine
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"
mkdir -p data logs/signals logs/executions exports
if [ -d ".venv" ]; then source .venv/bin/activate; fi
echo "Starting TTrade engine..."
echo "  Project: $PROJECT_DIR"
echo "  Mode: ${1:-MANUAL_APPROVAL}"
echo ""
if [ "${1:-}" = "--paper" ]; then
    python -m engine.cli run --paper
else
    python -m engine.cli run
fi
