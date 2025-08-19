#! /usr/bin/env python3
"""
Combined build script with version guard:

- Fetches the latest Bedrock Linux server URL + version
- Skips build if that version was already built (tracked in a local file)
- Downloads the ZIP with curl (headers included for reliability)
- Logs into Docker (using --password-stdin)
- Builds and pushes the Docker image
- Optionally commits & pushes changes to Git (skips if no staged changes)
- On success, writes the built version to the version file

Environment overrides:
  DOCKER_USERNAME         default: "jackclark1123"
  DOCKER_IMAGE            default: "<DOCKER_USERNAME>/bedrockserver"
  DOCKER_PASSWORD_FILE    default: "pass"
  BEDROCK_ZIP             default: "bedrock-server.zip"
  BEDROCK_VERSION_FILE    default: "built_version.txt"
  FORCE_BUILD             if set to 1/true/yes, forces build even if version matches
"""
import os
import shlex
import subprocess
import time
from datetime import datetime
from pathlib import Path

import requests


def run(cmd, **kwargs):
    # Pretty print the command being run (without sensitive inputs)
    printable = " ".join(shlex.quote(str(c)) for c in cmd)
    print(f"$ {printable}")
    return subprocess.run(cmd, check=True, **kwargs)


def truthy(val: str) -> bool:
    print(val)
    return str(val).strip().lower() in {"1", "true", "yes", "y", "on"} if val is not None else False


def get_latest_linux_bedrock_url():
    api_url = "https://net-secondary.web.minecraft-services.net/api/v1.0/download/links"
    resp = requests.get(api_url)
    resp.raise_for_status()
    data = resp.json()
    links = data.get("result", {}).get("links", [])
    linux = next((entry for entry in links if entry.get("downloadType") == "serverBedrockLinux"), None)
    if not linux:
        raise RuntimeError("Could not find Bedrock Linux server download link")
    download_url = linux["downloadUrl"]
    version = linux.get("version", "unknown")
    return download_url, version


def read_prev_version(version_file: Path) -> str:
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
        # Ignore logout failures
        print("⚠️  docker logout failed (continuing).")


def docker_login(username: str, pass_file: str = "pass"):
    # Use --password-stdin instead of -p to avoid leaking secrets to process list
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
    # Stage everything
    run(["git", "add", "-A"])
    # Check if there are staged changes; if none, skip commit
    diff = subprocess.run(["git", "diff", "--cached", "--quiet"])
    if diff.returncode == 0:
        print("🟰 No staged changes; skipping git commit/push.")
        return
    message = f"Auto-build-{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
    run(["git", "commit", "-m", message])
    run(["git", "push"])


def main():
    # Config (env-overridable to avoid hardcoding)
    username = os.getenv("DOCKER_USERNAME", "jackclark1123")
    image = os.getenv("DOCKER_IMAGE", f"{username}/bedrockserver")
    pass_file = os.getenv("DOCKER_PASSWORD_FILE", "pass")
    output_zip = os.getenv("BEDROCK_ZIP", "bedrock-server.zip")
    version_file = Path(os.getenv("BEDROCK_VERSION_FILE", "built_version.txt"))
    force_build = truthy(os.getenv("FORCE_BUILD")) 
    print(force_build)

    # Discover latest URL + version
    try:
        download_url, version = get_latest_linux_bedrock_url()
        print(f"🎉 Latest version: {version}")
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

    # Download if we have a URL
    if download_url:
        try:
            download_with_curl(download_url, output_zip)
        except Exception as e:
            print(f"❌ Download error: {e}")
            # If download fails, abort build to avoid pushing stale image.
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

    # Git add/commit/push (if there are changes)
    if built_ok:
        try:
            git_add_commit_push()
        except subprocess.CalledProcessError as e:
            # Non-fatal for version recording
            print(f"⚠️  Git step failed: {e}")

    # Record version only if build succeeded and version is known
    if built_ok and version != "unknown":
        try:
            write_version_atomic(version_file, version)
        except Exception as e:
            print(f"⚠️  Could not write version file: {e}")


if __name__ == "__main__":
    main()
