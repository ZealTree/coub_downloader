"""Download the pinned FFmpeg binaries used by both native builds."""
import hashlib
from pathlib import Path
import shutil
import sys
import tarfile
import urllib.request
import zipfile

FFMPEG = {
    "win32": ("ffmpeg-n9.0.2-14-gebafaee10a-win64-gpl-9.0.zip",
              "09170e52cb657f184ba4da2f42567cf2841b661cd9bb5f46ffe4481eb8e6d841"),
    "linux": ("ffmpeg-n9.0.2-14-gebafaee10a-linux64-gpl-9.0.tar.xz",
              "58e27dab85141ff1e08f43488b7700cc4443e17571bbee809edd6486d9dfd9b2"),
}
DOWNLOAD_BASE = "https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2026-09-28-13-06/"


def sha256(path):
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def download_ffmpeg(work):
    name, expected = FFMPEG[sys.platform]
    archive = work / name
    if not archive.exists() or sha256(archive) != expected:
        # Download public binaries without authentication headers.
        with urllib.request.urlopen(DOWNLOAD_BASE + name, timeout=120) as response, archive.open("wb") as out:
            shutil.copyfileobj(response, out)
    if sha256(archive) != expected:
        raise RuntimeError("FFmpeg archive SHA256 mismatch")
    destination = work / "ffmpeg"
    destination.mkdir(exist_ok=True)
    # Extract only the two executables and legal notices, never archive paths.
    suffix = ".exe" if sys.platform == "win32" else ""
    wanted = {"ffmpeg" + suffix, "ffprobe" + suffix, "LICENSE.txt", "LICENSE", "README.txt", "README.md"}
    if name.endswith(".zip"):
        with zipfile.ZipFile(archive) as package:
            for info in package.infolist():
                leaf = Path(info.filename).name
                if not info.is_dir() and leaf in wanted:
                    (destination / leaf).write_bytes(package.read(info))
    else:
        with tarfile.open(archive) as package:
            for info in package:
                leaf = Path(info.name).name
                if info.isfile() and leaf in wanted:
                    with package.extractfile(info) as source:
                        (destination / leaf).write_bytes(source.read())
    for tool in ("ffmpeg", "ffprobe"):
        executable = destination / (tool + suffix)
        if not executable.is_file():
            raise RuntimeError(f"Archive lacks {tool}")
        executable.chmod(0o755)
    if not any((destination / name).is_file() for name in ("LICENSE", "LICENSE.txt")):
        raise RuntimeError("Archive lacks FFmpeg license")
    return destination


if __name__ == "__main__":
    work = Path("build/ffmpeg-download")
    work.mkdir(parents=True, exist_ok=True)
    print(download_ffmpeg(work).resolve())
