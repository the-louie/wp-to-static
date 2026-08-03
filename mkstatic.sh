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

# More than one user builds this repo, so the venv has to be usable by all of
# them. uv defaults to its own managed interpreter under ~/.local/share/uv,
# and a home directory is typically mode 700 -- so a venv built that way works
# only for whoever created it, and everyone else sees "no virtualenv" because
# the interpreter symlink is untraversable. Pin a system python instead.
SYSTEM_PYTHON=$(command -v python3 || true)

usable() {
    [ -x "$PY" ] && "$PY" -c '' > /dev/null 2>&1
}

# Test the directory, not the interpreter: -e follows symlinks, so a venv whose
# python points somewhere unreadable (or nowhere) looks absent rather than
# broken, and uv would then build on top of the wreckage.
if [ -d "$VENV" ] && ! usable; then
    echo "==> $VENV exists but its interpreter does not work for $(id -un)" >&2
    echo "    $PY -> $(readlink "$PY" 2>/dev/null || echo 'missing')" >&2
    echo "    rebuilding it against $SYSTEM_PYTHON" >&2
    rm -rf "$VENV"
fi

if ! usable; then
    echo "==> creating $VENV" >&2
    if ! command -v uv > /dev/null 2>&1; then
        echo "uv is not installed, and it is what builds the virtualenv." >&2
        echo "Note that 'python3 -m venv' is not a fallback here: this system" >&2
        echo "has no ensurepip, so the venv would come up without pip." >&2
        echo "Install uv:  curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
        exit 1
    fi
    [ -n "$SYSTEM_PYTHON" ] || { echo "no python3 on PATH" >&2; exit 1; }
    uv venv --python "$SYSTEM_PYTHON" "$VENV" >&2
    uv pip install --python "$PY" -e '.[dev]' >&2
    # Let the other builders use what we just made.
    chgrp -R "$(stat -c '%G' .)" "$VENV" 2>/dev/null || true
    chmod -R g+rwX "$VENV" 2>/dev/null || true
fi

# --upload first so a later --skip upload can still turn it off.
exec "$PY" -m wp_to_static --upload "$@"
