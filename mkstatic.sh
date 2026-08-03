#!/usr/bin/env bash
#
# Build louie.se and publish it.
#
#   ./mkstatic.sh                    build and upload
#   ./mkstatic.sh --dry-run          build, then show what would be uploaded
#   ./mkstatic.sh --skip upload      build only
#   ./mkstatic.sh --crosscheck-all   verify every feed, not a sample of five
#
# Anything you pass is handed straight to the generator, so `--help` lists the
# rest. This exists only so the venv is not something to remember; the build
# itself lives in wp_to_static/.
#
# Publishing is safe to run by habit: the verify stage refuses to upload a build
# that lost pages, and any error stops it before rsync runs.

set -euo pipefail

cd "$(dirname "$0")"

VENV=.venv
PY="$VENV/bin/python"

if [ ! -x "$PY" ]; then
    echo "==> no virtualenv at $VENV, creating one" >&2
    if ! command -v uv > /dev/null 2>&1; then
        echo "uv is not installed, and it is what builds the virtualenv." >&2
        echo "Install it, or create the venv by hand:" >&2
        echo "    python3 -m venv $VENV && $PY -m pip install -e ." >&2
        exit 1
    fi
    uv venv "$VENV" >&2
    uv pip install --python "$PY" -e '.[dev]' >&2
fi

# --upload first so a later --skip upload can still turn it off.
exec "$PY" -m wp_to_static --upload "$@"
