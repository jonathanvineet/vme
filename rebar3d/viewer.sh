#!/bin/sh
# Launch the rebar 3D viewer locally. Pass --rebuild to re-run the DWG pipeline.
cd "$(dirname "$0")" && exec python3 viewer.py "$@"
