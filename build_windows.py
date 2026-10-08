"""Native PyInstaller build for Windows and Linux (historical script name)."""
import argparse
import os
from pathlib import Path
import sys
import platform
from ci.version import ci_ref, read_version


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ffmpeg-dir", required=True, type=Path,
                        help="Directory containing native ffmpeg, ffprobe and LICENSE/ LICENSE.txt")
    args = parser.parse_args()
    if sys.platform not in ("win32", "linux") or platform.machine().lower() not in ("amd64", "x86_64"):
        parser.error("Build natively on Windows/Linux x64")
    windows = sys.platform == "win32"
    suffix = ".exe" if windows else ""
    target = "windows-x64" if windows else "linux-x86_64"
    root = Path(__file__).resolve().parent
    binaries = args.ffmpeg_dir.resolve()
    for name in ("ffmpeg" + suffix, "ffprobe" + suffix):
        if not (binaries / name).is_file():
            parser.error(f"Missing {binaries / name}")
    license_path = next((p for p in (binaries / "LICENSE", binaries / "LICENSE.txt", binaries.parent / "LICENSE") if p.is_file()), None)
    if license_path is None:
        parser.error("FFmpeg LICENSE or LICENSE.txt is required")
    version = read_version(root / "version.txt", ci_ref())
    # Prevent unrelated developer-tool DLLs from entering Windows bundles.
    if windows:
        system_root = Path(os.environ["SYSTEMROOT"])
        os.environ["PATH"] = os.pathsep.join([sys.base_prefix, str(system_root / "System32"), str(system_root)])
    import PyInstaller.__main__
    options = [
        str(root / "ci" / "launcher.py"), "--noconfirm", "--clean", "--onefile",
        "--paths", str(root),
        "--name", f"CoubDownloader-{version}-{target}",
        "--distpath", str(root / "dist"), "--workpath", str(root / "build"),
        "--specpath", str(root / "build"),
        "--add-data", str(root / "assets") + os.pathsep + "assets",
        "--add-data", str(root / "version.txt") + os.pathsep + ".",
        "--add-data", str(license_path) + os.pathsep + "licenses/ffmpeg",
    ]
    if windows:
        from PyInstaller.utils.win32.versioninfo import (VSVersionInfo, FixedFileInfo,
                                                       StringFileInfo, StringTable, StringStruct)
        parts = tuple(map(int, version.split("."))) + (0,)
        metadata = VSVersionInfo(ffi=FixedFileInfo(filevers=parts, prodvers=parts), kids=[
            StringFileInfo([StringTable("040904B0", [
                StringStruct("ProductName", "Coub Downloader"),
                StringStruct("ProductVersion", version), StringStruct("FileVersion", version),
            ])])
        ])
        version_file = root / "build" / "version-info.txt"
        version_file.parent.mkdir(exist_ok=True)
        version_file.write_text(str(metadata), encoding="utf-8")
        options += ["--windowed", "--icon", str(root / "assets" / "icon.ico"),
                    "--version-file", str(version_file)]
    for name in ("ffmpeg" + suffix, "ffprobe" + suffix):
        options += ["--add-binary", str(binaries / name) + os.pathsep + "bin"]
    for package in ("PyQt6", "PyQt6-Qt6", "PyQt6-sip", "requests", "ffmpeg-python", "certifi"):
        options += ["--copy-metadata", package]
    PyInstaller.__main__.run(options)


if __name__ == "__main__":
    main()
