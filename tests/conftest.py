from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from wp_to_static.config import Config  # noqa: E402


@pytest.fixture
def cfg(tmp_path: Path) -> Config:
    """Config matching what the bash pipeline assumed.

    Pinned rather than inherited from the defaults so the A/B against the sed
    scripts stays a like-for-like comparison: the bash scripts only ever knew
    one host ($LOCALURL) and have no concept of legacy hosts, so legacy_hosts
    must be empty here. Legacy-host behaviour is tested separately, against a
    Config that opts into it.
    """
    return Config(
        repo_dir=REPO,
        base_dir=tmp_path / "output",
        local_url="localhost:8000",
        local_scheme="http",
        legacy_hosts=(),
    )


@pytest.fixture
def repo() -> Path:
    return REPO


# A page shaped like what WordPress actually emits, used both for the Python
# tests and for the A/B comparison against the original sed scripts.
WP_PAGE = """<!DOCTYPE html>
<html lang="sv"><head>
<meta charset="UTF-8">
<title>Nagot inlagg</title>
<link rel="alternate" type="application/rss+xml" title="louie.se &raquo; Flode" href="http://localhost:8000/feed/" />
<link rel="alternate" type="application/rss+xml" title="louie.se &raquo; Kommentarsflode" href="http://localhost:8000/comments/feed/" />
<link rel="alternate" type="application/atom+xml" title="louie.se Atom" href="http://localhost:8000/feed/atom/" />
<link rel="canonical" href="http://localhost:8000/nagot-inlagg/" />
<link rel='shortlink' href='http://localhost:8000/?p=1234' />
<meta property="og:url" content="http://localhost:8000/nagot-inlagg/" />
<meta property="og:image" content="http://localhost:8000/wp-content/uploads/bild.png" />
<meta name="twitter:image" content="http://localhost:8000/wp-content/uploads/bild.png" />
<meta name="generator" content="WordPress 6.1.1" />
<link rel="stylesheet" href="http://localhost:8000/wp-content/themes/eisai-child/assets/theme.css?ver=1.2" />
<script src="http://localhost:8000/wp-includes/js/jquery.min.js?ver=3.6.1"></script>
</head>
<body>
<a href="http://localhost:8000/annat/index.html">annat</a>
<p>Se aven <a href="http://localhost:8000/">startsidan</a>.</p>
<script>var cfg = {"home":"http:\\/\\/localhost:8000\\/","v":1};</script>
</body></html>
"""
