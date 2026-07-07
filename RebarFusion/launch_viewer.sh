#!/usr/bin/env bash
# launch_viewer.sh — launch the RebarFusion Engineering Viewer
# Usage: ./launch_viewer.sh [project_directory]
# Example: ./launch_viewer.sh test_project

set -e

# Always run from the RebarFusion root regardless of where the script is called from
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PROJECT="${1:-test_project}"

echo "RebarFusion Engineering Viewer"
echo "Project: $SCRIPT_DIR/$PROJECT"
echo "------------------------------"

PYTHONPATH=. .venv/bin/python viewer/app.py "$PROJECT"
