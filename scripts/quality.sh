#!/bin/bash
# Run all quality checks: formatting, linting, and tests

set -e

cd "$(dirname "$0")/.."

echo "=== Running Code Quality Checks ==="
echo

echo "1. Checking code formatting with black..."
uv run black --check backend/ main.py
echo "   Black: OK"
echo

echo "2. Running ruff linter..."
uv run ruff check backend/ main.py
echo "   Ruff: OK"
echo

echo "3. Running tests..."
cd backend && uv run pytest -v
echo "   Tests: OK"
echo

echo "=== All Quality Checks Passed ==="
