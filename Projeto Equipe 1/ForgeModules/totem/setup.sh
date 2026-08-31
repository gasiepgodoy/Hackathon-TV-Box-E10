#!/usr/bin/env bash
# Shell wrapper for Mina Virtual Assistant setup
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON_CMD="python3"
if ! command -v python3 &> /dev/null; then
    PYTHON_CMD="python"
fi

echo "=== Starting Mina Assistant Cross-Platform Installation ==="
$PYTHON_CMD install.py "$@"
