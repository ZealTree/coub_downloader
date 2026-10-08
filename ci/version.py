"""Validate the single source of version, and its release tag when present."""
import os
from pathlib import Path
import re

STABLE = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")


def ci_ref():
    """Return the GitHub ref for release tag validation."""
    return os.environ.get("GITHUB_REF", "")


def read_version(path=Path("version.txt"), ref=""):
    version = path.read_text(encoding="utf-8-sig").strip()
    if not STABLE.fullmatch(version):
        raise ValueError("version.txt must contain MAJOR.MINOR.PATCH without leading zeros")
    if ref.startswith("refs/tags/") and ref != "refs/tags/v" + version:
        raise ValueError(f"Release tag must equal v{version} from version.txt")
    return version


if __name__ == "__main__":
    print(read_version(ref=ci_ref()))
