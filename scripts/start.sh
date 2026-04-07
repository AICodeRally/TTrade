#!/bin/bash
# Start TTrade engine
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"
mkdir -p data logs/signals logs/executions exports
export PYTHONUNBUFFERED=1

# Use venv entry point directly (works under launchd where PATH is limited)
TTRADE="$PROJECT_DIR/.venv/bin/ttrade"
if [ ! -f "$TTRADE" ]; then
    echo "ERROR: ttrade not found at $TTRADE — run 'pip install -e .'" >&2
    exit 1
fi

echo "Starting TTrade engine..."
echo "  Project: $PROJECT_DIR"
echo "  Mode: ${1:-MANUAL_APPROVAL}"
echo ""
if [ "${1:-}" = "--paper" ]; then
    exec "$TTRADE" run --paper
else
    exec "$TTRADE" run
fi
