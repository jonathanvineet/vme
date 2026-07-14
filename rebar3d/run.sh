#!/bin/sh
# Run the rebar3d pipeline on the drawings in a folder.
#
# Usage: ./run.sh <drawings-folder> [outdir]
#   outdir defaults to ./out
#
# Only the (R) reinforcement sheets carry rebar, so when a folder mixes
# mould (M) and reinforcement (R) drawings, only the (R) ones are used.
# Pass --all to process every DWG/DXF regardless.
set -e

all=0
if [ "$1" = "--all" ]; then
    all=1
    shift
fi

if [ -z "$1" ]; then
    echo "usage: $0 [--all] <drawings-folder> [outdir]" >&2
    exit 1
fi

dir=$1
out=${2:-out}

if [ ! -d "$dir" ]; then
    echo "error: '$dir' is not a directory" >&2
    exit 1
fi

cd "$(dirname "$0")"

# Collect drawings, skipping .dxf twins of a .dwg with the same stem.
files=$(mktemp)
trap 'rm -f "$files"' EXIT
for f in "$dir"/*.dwg "$dir"/*.DWG; do
    [ -e "$f" ] && printf '%s\n' "$f" >> "$files"
done
for f in "$dir"/*.dxf "$dir"/*.DXF; do
    [ -e "$f" ] || continue
    stem=${f%.*}
    [ -e "$stem.dwg" ] || [ -e "$stem.DWG" ] || printf '%s\n' "$f" >> "$files"
done

# Prefer the (R) reinforcement sheets unless --all or none exist.
if [ "$all" -eq 0 ] && grep -q '(R)' "$files"; then
    grep '(R)' "$files" > "$files.r" && mv "$files.r" "$files"
fi

set --
while IFS= read -r f; do
    set -- "$@" "$f"
done < "$files"

if [ $# -eq 0 ]; then
    echo "error: no .dwg or .dxf files found in '$dir'" >&2
    exit 1
fi

echo "processing $# drawing(s) from $dir"
python3 -m rebar3d.cli "$@" -o "$out"
open "$out/viewer.html"
