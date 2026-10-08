"""Locate and validate FFmpeg executables for source and frozen app runs."""
import os
from pathlib import Path
import shutil
import subprocess
import sys


def windows_process_options():
    """Return subprocess flags that suppress an extra Windows console window."""
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def tool_candidates(name, *, frozen_dir=None, which=shutil.which, windows=None):
    """Return bundled first, then PATH candidates, without duplicate paths."""
    if windows is None:
        windows = os.name == "nt"
    if frozen_dir is None and getattr(sys, "frozen", False):
        frozen_dir = getattr(sys, "_MEIPASS", None)

    suffix = ".exe" if windows else ""
    candidates = []
    if frozen_dir:
        bundled = Path(frozen_dir) / "bin" / (name + suffix)
        if bundled.is_file():
            candidates.append(str(bundled))

    system_tool = which(name)
    if system_tool and system_tool not in candidates:
        candidates.append(system_tool)
    return candidates


def find_working_tool(name, *, frozen_dir=None, which=shutil.which,
                      run=subprocess.run, windows=None):
    """Return the first executable that responds successfully to ``-version``."""
    flags = windows_process_options()
    for candidate in tool_candidates(name, frozen_dir=frozen_dir, which=which,
                                     windows=windows):
        try:
            result = run([candidate, "-version"], stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, timeout=15, **flags)
            if result.returncode == 0:
                return candidate
        except (OSError, subprocess.SubprocessError):
            continue
    return None


def find_media_tools(*, frozen_dir=None, which=shutil.which, run=subprocess.run,
                     windows=None):
    """Find working ffmpeg and ffprobe paths, preferring bundled executables."""
    ffmpeg_path = find_working_tool("ffmpeg", frozen_dir=frozen_dir, which=which,
                                    run=run, windows=windows)
    ffprobe_path = find_working_tool("ffprobe", frozen_dir=frozen_dir, which=which,
                                    run=run, windows=windows)
    if ffmpeg_path and ffprobe_path:
        return ffmpeg_path, ffprobe_path
    return None
