#!/bin/bash
# Format all Python files with black and ruff

set -e

cd "$(dirname "$0")/.."

echo "Running black formatter..."
uv run black backend/ main.py

echo "Running ruff formatter (import sorting)..."
uv run ruff check --fix backend/ main.py

echo "Formatting complete!"
