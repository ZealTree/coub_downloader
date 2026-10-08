"""Publish native assets through GitHub CLI."""
import json
import os
from pathlib import Path
import subprocess
from version import read_version

REPOSITORY = "ZealTree/coub_downloader"


def gh(*args):
    return subprocess.check_output(
        ["gh", *args, "--repo", REPOSITORY], text=True,
    ).strip()


def publish(version, sha, assets):
    tag = "v" + version
    actual = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True,
    ).strip()
    tagged = subprocess.check_output(
        ["git", "rev-parse", tag + "^{commit}"], text=True,
    ).strip()
    if actual != sha or tagged != sha:
        raise ValueError("Release checkout and tag must match the triggering commit")
    # --verify-tag prevents accidental creation of a tag from a different branch.
    releases = json.loads(gh("release", "list", "--limit", "1000",
                             "--json", "tagName,isDraft"))
    release = next((r for r in releases if r["tagName"] == tag), None)
    if release and not release["isDraft"]:
        print("Release already published; leaving it unchanged")
        return
    if release is None:
        gh("release", "create", tag, "--verify-tag", "--target", sha,
           "--draft", "--title", tag, "--notes",
           f"Coub Downloader {version}. Native Windows x64 and Linux x86_64 executables.")
    gh("release", "upload", tag, *(str(p) for p in assets), "--clobber")
    uploaded = json.loads(gh("release", "view", tag, "--json", "assets"))["assets"]
    sizes = {a["name"]: a["size"] for a in uploaded}
    if any(sizes.get(p.name) != p.stat().st_size for p in assets):
        raise RuntimeError("Release asset verification failed; keeping draft")
    gh("release", "edit", tag, "--draft=false")


def main():
    ref = os.environ.get("GITHUB_REF", "")
    if (os.environ.get("GITHUB_EVENT_NAME") != "push"
            or not ref.startswith("refs/tags/v")
            or os.environ.get("GITHUB_REPOSITORY", "").lower() != REPOSITORY.lower()):
        raise SystemExit("Publishing requires a version tag push in the configured GitHub repository")
    version = read_version(ref=ref)
    assets = [Path(f"dist/CoubDownloader-{version}-windows-x64.exe"),
              Path(f"dist/CoubDownloader-{version}-linux-x86_64")]
    if any(not p.is_file() or p.stat().st_size == 0 for p in assets):
        raise SystemExit("Both executables are required")
    publish(version, os.environ["GITHUB_SHA"], assets)


if __name__ == "__main__":
    main()
