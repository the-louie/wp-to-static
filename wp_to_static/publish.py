"""Upload the finished tree.

NOTE: uploading is done manually, over ssh as a different user with its own
keys. This module has therefore never been run successfully and is not part of
the normal flow -- `--upload` is opt-in and off by default. Treat it as
unverified until someone runs it with `--dry-run` and reads the file list.
"""

from __future__ import annotations

import subprocess

from .config import Config


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
    command = [
        "rsync",
        "-e",
        f"ssh -i {cfg.ssh_key}",
        "-av",
        f"{cfg.site_dir}/",
        cfg.upload_target,
    ]
    if dry_run:
        command.insert(1, "--dry-run")
    result = subprocess.run(command)
    if result.returncode != 0:
        raise PublishError(f"rsync failed with status {result.returncode}")
