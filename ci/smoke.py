"""Launch the built executable without relying on external Python/FFmpeg."""
import json
import os
from pathlib import Path
import subprocess
import sys
from version import read_version
from PyInstaller.archive.readers import CArchiveReader

version = read_version()
windows = sys.platform == "win32"
target = "windows-x64.exe" if windows else "linux-x86_64"
binary = Path(f"dist/CoubDownloader-{version}-{target}").resolve()
# Check the actual executable and its embedded payload before starting it.
with binary.open("rb") as stream:
    magic = stream.read(4)
if (windows and magic[:2] != b"MZ") or (not windows and magic != b"\x7fELF"):
    raise SystemExit("Build output is not a native executable")
archive = CArchiveReader(str(binary))
suffix = ".exe" if windows else ""
for member in ("bin/ffmpeg" + suffix, "bin/ffprobe" + suffix, "version.txt",
               "assets/icon.ico", "assets/icon.png", "assets/checkmark.svg", "assets/chevron-down.svg"):
    if member not in {name.replace("\\", "/") for name in archive.toc}:
        raise SystemExit("Executable payload is missing " + member)
report = Path("build/smoke.json").resolve()
env = dict(os.environ)
env["QT_QPA_PLATFORM"] = "offscreen" if windows else "xcb"
env["PATH"] = str(Path(os.environ["SYSTEMROOT"]) / "System32") if windows else "/usr/bin:/bin"
for key in ("PYTHONPATH", "PYTHONHOME", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH"):
    env.pop(key, None)
flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if windows else {}
command = [str(binary), "--smoke-test", str(report)]
if not windows:
    command = ["xvfb-run", "-a", *command]
subprocess.run(command, cwd=binary.parent,
               env=env, check=True, timeout=120, **flags)
result = json.loads(report.read_text())
if (not result["success"] or result["version"] != version or not result["frozen"]
        or result["bundled_tools"] != ["ffmpeg", "ffprobe"]):
    raise SystemExit("Packaged executable smoke test failed")
print("Executable verified:", binary.name)
