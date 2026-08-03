"""Upload the finished tree.

NOTE: uploading is done manually, over ssh as a different user with its own
keys. This module has therefore never been run successfully and is not part of
the normal flow -- `--upload` is opt-in and off by default. Treat it as
unverified until someone runs it with `--dry-run` and reads the file list.
"""

from __future__ import annotations

import subprocess
import sys

from .config import Config

# The codes worth naming. 23 in particular reads as a generic failure but
# usually means the receiving user could not write or chown specific files.
KNOWN_CODES = {
    1: "syntax or usage error",
    2: "protocol incompatibility",
    5: "error starting client-server protocol (often ssh failing to connect)",
    10: "error in socket I/O",
    11: "error in file I/O",
    12: "error in rsync protocol data stream",
    23: (
        "partial transfer due to error -- some files were not transferred. "
        "Most often the remote user cannot overwrite existing files, or cannot "
        "set their permissions/ownership"
    ),
    24: "partial transfer due to vanished source files",
    30: "timeout in data send/receive",
    255: "ssh failed (host unreachable, auth refused, unknown host)",
}


class PublishError(RuntimeError):
    pass


def upload(cfg: Config, *, dry_run: bool = False) -> None:
    """rsync the site tree to the server.

    Deliberately without --delete, and do not add it without an audit.

    The document root holds hand-placed content that this generator does not
    produce and knows nothing about -- /dumpster/ contains standalone JS pages
    (e.g. /dumpster/misc/jpeg-distort/) that posts link to, and ACME challenges
    live under /.well-known/. --delete would destroy all of it on the next
    build.

    The cost of leaving it out is that stale files live forever: a renamed post
    keeps its old directory, which is why some old URLs still resolve on the
    live site even though nothing generates them any more.

    TODO: no good fix found yet. --delete with --exclude for each hand-placed
    path would work but silently rots as soon as someone adds a new one. A
    manifest of generated files, diffed against the previous build so only
    files this generator created are removed, is the shape that would actually
    be safe -- the state file written by the verify stage is the natural place
    to keep it.
    """
    # No -e: the ssh identity and any host options come from the uploading
    # user's ~/.ssh/config. A key path has no business being in the repo.
    #
    # --omit-dir-times because -a implies -t, and setting a directory's mtime
    # requires owning it. The web root contains directories this user does not
    # own -- .well-known/ belongs to the ACME client -- so without it every such
    # directory produces "failed to set times: Operation not permitted" and
    # turns a clean upload into exit 23. Directory mtimes do not affect serving.
    command = ["rsync", "-av", "--omit-dir-times", f"{cfg.site_dir}/", cfg.upload_target]
    if dry_run:
        command.insert(1, "--dry-run")

    # stdout stays on the terminal (it is the file list); stderr is captured so
    # the per-file failures can be reported instead of scrolling past behind a
    # bare exit code. rsync writes one line per problem file, then a summary.
    result = subprocess.run(command, stderr=subprocess.PIPE, text=True)
    stderr = (result.stderr or "").strip()
    if stderr:
        print(stderr, file=sys.stderr)

    if result.returncode == 0:
        return

    raise PublishError(explain(result.returncode, stderr))


def explain(code: int, stderr: str) -> str:
    """Turn an rsync exit code and its stderr into something actionable."""
    detail = KNOWN_CODES.get(code, "see rsync(1) for this exit code")
    lines = [
        line
        for line in stderr.splitlines()
        if line.startswith("rsync:") or "failed" in line or "denied" in line
    ]
    message = f"rsync exited {code}: {detail}"
    if lines:
        shown = lines[:8]
        message += "\n  " + "\n  ".join(shown)
        if len(lines) > len(shown):
            message += f"\n  ... and {len(lines) - len(shown)} more"
    return message
