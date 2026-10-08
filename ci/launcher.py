"""Packaging entry point; application sources stay untouched."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import shutil
from unittest.mock import patch
from media_tools import find_media_tools

if getattr(sys, "frozen", False):
    os.environ["PATH"] = str(Path(sys._MEIPASS) / "bin") + os.pathsep + os.environ.get("PATH", "")

import coub_downloader_gui as app

RESOURCE_ROOT = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
VERSION = (RESOURCE_ROOT / "version.txt").read_text(encoding="utf-8-sig").strip()


def smoke_test(report, require_frozen=True):
    flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    result = {"success": False, "platform": sys.platform, "version": VERSION,
              "frozen": bool(getattr(sys, "frozen", False)), "bundled_tools": []}
    try:
        qt = app.QApplication.instance() or app.QApplication([])
        icon_name = "assets/icon.ico" if sys.platform == "win32" else "assets/icon.png"
        icon_path = app.resource_path(icon_name)
        if not Path(icon_path).is_file() or app.QIcon(str(icon_path)).isNull():
            raise RuntimeError(f"Application icon is missing or unreadable: {icon_path}")
        for name in ("assets/checkmark.svg", "assets/chevron-down.svg"):
            if app.QIcon(str(app.resource_path(name))).pixmap(16, 16).isNull():
                raise RuntimeError("Control icon is unreadable: " + name)
        if require_frozen and not result["frozen"]:
            raise RuntimeError("Smoke test must run a packaged executable")
        resolved = find_media_tools()
        if resolved is None:
            raise RuntimeError("Could not resolve working FFmpeg and ffprobe")
        tools = dict(zip(("ffmpeg", "ffprobe"), resolved))
        for name, path in tools.items():
            expected = Path(getattr(sys, "_MEIPASS", RESOURCE_ROOT)) / "bin" / (name + (".exe" if sys.platform == "win32" else ""))
            if result["frozen"] and Path(path) != expected:
                raise RuntimeError(f"Did not resolve bundled {name}: {path}")
            subprocess.run([path, "-version"], capture_output=True, check=True, timeout=30, **flags)
            result["bundled_tools"].append(name)
        with tempfile.TemporaryDirectory(prefix="coub-smoke-") as directory:
            with patch.object(app, "get_default_download_directory", return_value=directory):
                window = app.CoubDownloaderGUI()
            window.show()
            qt.processEvents()
            if window.windowIcon().isNull() or qt.windowIcon().isNull():
                raise RuntimeError("Application icon is not installed")
            result["qt_platform"] = qt.platformName()
            video = str(Path(directory) / "video.mp4")
            audio = str(Path(directory) / "audio.m4a")
            for arguments in [
                ["-f", "lavfi", "-i", "color=c=black:s=32x32:r=25:d=1", "-c:v", "mpeg4", video],
                ["-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-c:a", "aac", audio],
            ]:
                subprocess.run([tools["ffmpeg"], "-y", "-loglevel", "error"] + arguments,
                               capture_output=True, check=True, timeout=30, **flags)
            def download(url, path):
                shutil.copyfile(url, path)
                yield 100
            result["modes"] = []
            for loop, expected in [(False, 1), (True, 3)]:
                output = Path(directory) / "output.mp4"
                worker = app.DownloadThread("offline", output.name, loop, "high", directory, *resolved)
                results, progress = [], []
                worker.finished_signal.connect(results.append)
                worker.progress_signal.connect(progress.append)
                with patch.object(app, "get_media_urls", return_value=(video, audio)), patch.object(app, "download_file", side_effect=download):
                    worker.run()
                if results != [True] or not any(80 < value < 100 for value in progress) or progress[-1] != 100:
                    raise RuntimeError("Downloader processing or progress failed")
                duration = float(app.probe_media(str(output), tools["ffprobe"])["format"]["duration"])
                if abs(duration - expected) > 0.3 or any(p.is_dir() for p in Path(directory).iterdir()):
                    raise RuntimeError("Unexpected duration or leftover temporary files")
                result["modes"].append({"loop": loop, "duration": duration})
            window.close()
        result["success"] = True
    except Exception as error:
        result["error"] = type(error).__name__ + ": " + str(error)
    Path(report).parent.mkdir(parents=True, exist_ok=True)
    Path(report).write_text(json.dumps(result), encoding="utf-8")
    return 0 if result["success"] else 1


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--smoke-test":
        sys.exit(smoke_test(sys.argv[2]))
    qt = app.QApplication(sys.argv)
    qt.setApplicationVersion(VERSION)
    window = app.CoubDownloaderGUI()
    window.show()
    sys.exit(qt.exec())
