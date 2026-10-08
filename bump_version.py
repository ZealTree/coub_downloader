"""Explicit SemVer update; version.txt is the only source of truth."""
import argparse
from pathlib import Path
from ci.version import STABLE


def bump_version(version, part="patch"):
    if not STABLE.fullmatch(version):
        raise ValueError("Expected MAJOR.MINOR.PATCH without leading zeros")
    major, minor, patch = map(int, version.split("."))
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError("Unknown SemVer part")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--part", choices=["major", "minor", "patch"], default="patch")
    args = parser.parse_args()
    path = Path(__file__).with_name("version.txt")
    old = path.read_text(encoding="utf-8-sig").strip()
    new = bump_version(old, args.part)
    path.write_text(new + "\n", encoding="utf-8")
    print(f"Version bumped from {old} to {new}")


if __name__ == "__main__":
    main()
