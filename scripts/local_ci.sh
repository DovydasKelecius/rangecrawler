#!/bin/bash

# Local CI check script for RangeCrawler

# Project root
PROJECT_ROOT=$(pwd)

# Activate virtual environment if it exists
if [ -d "$PROJECT_ROOT/venv" ]; then
    echo "Activating virtual environment..."
    source "$PROJECT_ROOT/venv/bin/activate"
else
    echo "Warning: No venv found at $PROJECT_ROOT/venv. Running with system python."
fi

export PYTHONPATH=$PROJECT_ROOT:$PROJECT_ROOT/src

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print section headers
section() {
    echo -e "\n${YELLOW}=== $1 ===${NC}"
}

# 1. Check for required tools
section "Checking Environment"
MISSING_TOOLS=()
for tool in ruff mypy bandit pytest prettier docker; do
    if ! command -v $tool &> /dev/null; then
        MISSING_TOOLS+=($tool)
    fi
done

if [ ${#MISSING_TOOLS[@]} -ne 0 ]; then
    echo -e "${RED}Warning: Some tools are missing: ${MISSING_TOOLS[*]}${NC}"
    echo "Please install them to run all checks."
fi

# 2. Ruff Fix
section "Running Ruff Fix"
if command -v ruff &> /dev/null; then
    ruff check . --fix
else
    echo "Skipping Ruff (not installed)."
fi

# 3. Prettier
section "Running Prettier"
if command -v prettier &> /dev/null; then
    prettier --write "**/*.{js,json,md,yml,yaml}"
else
    echo "Skipping Prettier (not installed)."
fi

# 4. Type Check (Mypy)
section "Type Checking (Mypy)"
if command -v mypy &> /dev/null; then
    mypy src/
else
    echo "Skipping Mypy (not installed)."
fi

# 5. Security Scan (Bandit)
section "Security Scan (Bandit)"
if command -v bandit &> /dev/null; then
    bandit -r src/
else
    echo "Skipping Bandit (not installed)."
fi

# 6. Unit Tests (Pytest)
section "Running Unit Tests (Pytest)"
if command -v pytest &> /dev/null; then
    pytest tests/
else
    echo "Skipping Pytest (not installed)."
fi

# 7. Docker Build (Optional)
section "Docker Build"
if [ "$SKIP_DOCKER" == "1" ]; then
    echo "Skipping Docker Build as requested."
elif command -v docker &> /dev/null; then
    docker build -t rangecrawler-broker:latest .
else
    echo "Skipping Docker Build (not installed or docker daemon not running)."
fi

echo -e "\n${GREEN}Local CI checks completed!${NC}"
