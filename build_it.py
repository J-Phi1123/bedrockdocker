#!/usr/bin/env python3
"""
Combined build script with version guard and filename-based version parsing.

Features:
- Calls the official Bedrock links API and finds the Linux server download.
- Extracts the version from the download URL filename (e.g., bedrock-server-1.21.102.1.zip -> 1.21.102.1).
- Skips build if that version was already built (tracked in a local file).
- Downloads the ZIP with curl (extra headers for reliability).
- Logs into Docker (using --password-stdin from a file).
- Builds and pushes the Docker image.
- Optionally commits & pushes changes to Git (skips if no staged changes).
- On success, writes the built version to the version file.

Environment overrides:
  DOCKER_USERNAME         default: "jackclark1123"
  DOCKER_IMAGE            default: "<DOCKER_USERNAME>/bedrockserver"
  DOCKER_PASSWORD_FILE    default: "pass"
  BEDROCK_ZIP             default: "bedrock-server.zip"
  BEDROCK_VERSION_FILE    default: "built_version.txt"
  FORCE_BUILD             if set to 1/true/yes, forces build even if version matches
  BEDROCK_VERSION_REGEX   optional: custom regex with one capture group for version
"""

import os
import re
import shlex
import subprocess
import time
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Optional
from urllib.parse import urlparse

import requests


# ------------------------- utilities -------------------------

def run(cmd, **kwargs):
    """Run a subprocess and echo the command (sans secrets)."""
    printable = " ".join(shlex.quote(str(c)) for c in cmd)
    print(f"$ {printable}")
    return subprocess.run(cmd, check=True, **kwargs)


def truthy(val: Optional[str]) -> bool:
    return (val or "").strip().lower() in {"1", "true", "yes", "y", "on"}


# ------------------------- version parsing -------------------------

def extract_version_from_url(url: str) -> Optional[str]:
    """
    Parse versions like:
      bedrock-server-1.21.102.1.zip
      bedrock_server-1.21.0.zip
      bedrock-server-v1.21.0.zip
    Returns just the numeric version, e.g., "1.21.102.1".

    You can override the regex via BEDROCK_VERSION_REGEX; it must have ONE capture group.
    """
    # Default regex: capture digits and dots after 'bedrock[-_]server' / optional 'v', before '.zip'
    default_pattern = r"bedrock[-_]?server[-_]?v?(\d+(?:\.\d+)+)\.zip(?:\?.*)?$"
    pattern = os.getenv("BEDROCK_VERSION_REGEX", default_pattern)

    try:
        name = PurePosixPath(urlparse(url).path).name  # e.g., "bedrock-server-1.21.102.1.zip"
        m = re.search(pattern, name, flags=re.IGNORECASE)
        if m:
            return m.group(1)
        # Fallback: try entire URL in case the filename is unusual
        m = re.search(pattern, url, flags=re.IGNORECASE)
        if m:
            return m.group(1)
    except Exception as e:
        print(f"⚠️  Version parse failed: {e}")
    return None


# ------------------------- bedrock links API -------------------------

def get_latest_linux_bedrock_url():
    """
    Calls the official links API, finds the 'serverBedrockLinux' entry,
    returns (download_url, version). Version is derived from the filename.
    """
    api_url = "https://net-secondary.web.minecraft-services.net/api/v1.0/download/links"
    resp = requests.get(api_url)
    resp.raise_for_status()
    data = resp.json()
    links = data.get("result", {}).get("links", [])
    linux = next((entry for entry in links if entry.get("downloadType") == "serverBedrockLinux"), None)
    if not linux:
        raise RuntimeError("Could not find Bedrock Linux server download link")

    download_url = linux["downloadUrl"]
    version = extract_version_from_url(download_url) or "unknown"

    print(f"🔎 Parsed version from URL: {version} (from {download_url})")
    return download_url, version


# ------------------------- version file helpers -------------------------

def read_prev_version(version_file: Path) -> Optional[str]:
    try:
        return version_file.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    except Exception as e:
        print(f"⚠️  Could not read version file {version_file}: {e}")
        return None


def write_version_atomic(version_file: Path, version: str) -> None:
    tmp = version_file.with_suffix(version_file.suffix + ".tmp")
    tmp.write_text(version + "\n", encoding="utf-8")
    tmp.replace(version_file)
    print(f"📝 Wrote built version {version} to {version_file}")


# ------------------------- actions -------------------------

def download_with_curl(download_url, output_file):
    curl_cmd = [
        "curl", "-s", "-k", "-X", "GET",
        "-H", "Host: www.minecraft.net",
        "-H", 'Sec-Ch-Ua: "Not:A-Brand";v="99", "Chromium";v="112"',
        "-H", "Sec-Ch-Ua-Mobile: ?0",
        "-H", 'Sec-Ch-Ua-Platform: "Windows"',
        "-H", "Upgrade-Insecure-Requests: 1",
        "-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.5615.50 Safari/537.36",
        "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "-H", "Sec-Fetch-Site: same-origin",
        "-H", "Sec-Fetch-Mode: navigate",
        "-H", "Sec-Fetch-User: ?1",
        "-H", "Sec-Fetch-Dest: document",
        "-H", "Referer: https://www.minecraft.net/en-us/download/server/bedrock",
        "-H", "Accept-Encoding: gzip, deflate",
        "-H", "Accept-Language: en-US,en;q=0.9",
        download_url,
        "-o", output_file
    ]
    print("➡ Running curl download...")
    run(curl_cmd)
    print(f"✅ Downloaded to {output_file}")


def docker_logout():
    try:
        run(["docker", "logout"])
    except subprocess.CalledProcessError:
        print("⚠️  docker logout failed (continuing).")


def docker_login(username: str, pass_file: str = "pass"):
    """
    Login using --password-stdin so the password doesn't show up in ps/arg logs.
    Reads the password from a file (default 'pass').
    """
    if not os.path.exists(pass_file):
        raise FileNotFoundError(f"Docker password file not found: {pass_file}")
    with open(pass_file, "rb") as f:
        password = f.read()
    print("🔐 Logging in to Docker (password via stdin)...")
    run(["docker", "login", "-u", username, "--password-stdin"], input=password)


def docker_build_and_push(image_tag: str):
    run(["docker", "build", "-t", image_tag, "."])
    run(["docker", "push", image_tag])


def git_add_commit_push():
    """
    Stages, then commits only if there are staged changes.
    (Note: consider .gitignore for large artifacts like the ZIP if you don't want them committed.)
    """
    run(["git", "add", "-A"])
    # If no staged changes, 'git diff --cached --quiet' returns 0
    diff = subprocess.run(["git", "diff", "--cached", "--quiet"])
    if diff.returncode == 0:
        print("🟰 No staged changes; skipping git commit/push.")
        return
    message = f"Auto-build-{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
    run(["git", "commit", "-m", message])
    run(["git", "push"])


# ------------------------- main -------------------------

def main():
    # Config (env-overridable)
    username = os.getenv("DOCKER_USERNAME", "jackclark1123")
    image = os.getenv("DOCKER_IMAGE", f"{username}/bedrockserver")
    pass_file = os.getenv("DOCKER_PASSWORD_FILE", "pass")
    output_zip = os.getenv("BEDROCK_ZIP", "bedrock-server.zip")
    version_file = Path(os.getenv("BEDROCK_VERSION_FILE", "built_version.txt"))
    force_build = truthy(os.getenv("FORCE_BUILD"))

    # Discover latest URL + version (version parsed from URL filename)
    try:
        download_url, version = get_latest_linux_bedrock_url()
        print(f"🎉 Latest version (parsed): {version}")
        print(f"🔗 Download URL: {download_url}")
    except Exception as e:
        print(f"❌ Error during Bedrock API check: {e}")
        # If we can't determine version, proceed with build attempt (can't guard).
        download_url, version = None, "unknown"

    # Version guard (skip build if same and not forced)
    prev = read_prev_version(version_file)
    if version != "unknown" and prev == version and not force_build:
        print(f"✅ Already built version {version}; skipping build. Set FORCE_BUILD=1 to override.")
        return

    # Download the ZIP (if we have a URL)
    if download_url:
        try:
            download_with_curl(download_url, output_zip)
        except Exception as e:
            print(f"❌ Download error: {e}")
            # Abort build to avoid pushing a stale/broken image.
            return

    time.sleep(2)

    built_ok = False

    # Docker: logout → login → build/push → logout
    docker_logout()
    try:
        docker_login(username, pass_file=pass_file)
        docker_build_and_push(image)
        built_ok = True
    except subprocess.CalledProcessError as e:
        print(f"❌ Docker step failed: {e}")
    finally:
        docker_logout()

    # Git add/commit/push (non-fatal if it fails)
    if built_ok:
        try:
            git_add_commit_push()
        except subprocess.CalledProcessError as e:
            print(f"⚠️  Git step failed: {e}")

    # Record version only if build succeeded and version is known
    if built_ok:
        try:
            write_version_atomic(version_file, version)
        except Exception as e:
            print(f"⚠️  Could not write version file: {e}")


if __name__ == "__main__":
    main()
