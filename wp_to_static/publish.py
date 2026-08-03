"""Upload the finished tree."""

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
