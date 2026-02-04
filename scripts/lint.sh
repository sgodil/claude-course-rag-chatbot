#!/bin/bash
# Run linting checks without making changes

set -e

cd "$(dirname "$0")/.."

echo "Checking code formatting with black..."
uv run black --check backend/ main.py

echo "Running ruff linter..."
uv run ruff check backend/ main.py

echo "All checks passed!"
