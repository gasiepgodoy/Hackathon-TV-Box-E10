#!/usr/bin/env bash
# Mina Virtual Assistant / Totem Module Installer
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON_CMD="python3"
if ! command -v python3 &> /dev/null; then
    PYTHON_CMD="python"
fi

echo "=== Starting Mina Assistant (Totem Module) Installation ==="
$PYTHON_CMD install.py "$@"
