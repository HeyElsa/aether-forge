from __future__ import annotations

import tomllib
from pathlib import Path

from aether_forge import __version__


def test_runtime_version_matches_package_metadata() -> None:
    pyproject = tomllib.loads((Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf8"))

    assert __version__ == pyproject["project"]["version"]
