"""Application resource and default download paths."""
from pathlib import Path
import sys


def default_download_dir(home=None):
    """Return the user's Downloads folder on Windows and Unix-like systems."""
    return (Path(home) if home is not None else Path.home()) / "Downloads"


def resource_path(relative_path, *, frozen_dir=None, source_root=None):
    """Resolve a bundled resource or its path in a source checkout."""
    if frozen_dir is None and getattr(sys, "frozen", False):
        frozen_dir = getattr(sys, "_MEIPASS", None)
    root = Path(frozen_dir) if frozen_dir else (
        Path(source_root) if source_root is not None
        else Path(__file__).resolve().parent
    )
    return root / relative_path
