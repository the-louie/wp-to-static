"""Upload the finished tree."""

from __future__ import annotations

import subprocess

from .config import Config


class PublishError(RuntimeError):
    pass


def upload(cfg: Config, *, dry_run: bool = False) -> None:
    """rsync the site tree to the server.

    Deliberately without --delete: adding it would also remove anything placed
    on the target by hand, ACME challenges in particular. Stale files are a
    known consequence, tracked separately.
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
