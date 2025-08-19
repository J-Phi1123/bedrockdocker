#! /usr/bin/env python3
"""
Combined build script:
- Fetches the latest Bedrock Linux server URL
- Downloads the ZIP with curl (headers included for reliability)
- Logs into Docker (using --password-stdin)
- Builds and pushes the Docker image
- Optionally commits & pushes changes to Git (skips if no staged changes)
"""
import os
import shlex
import subprocess
import time
from datetime import datetime

import requests


def run(cmd, **kwargs):
    # Pretty print the command being run (without sensitive inputs)
    printable = " ".join(shlex.quote(str(c)) for c in cmd)
    print(f"$ {printable}")
    return subprocess.run(cmd, check=True, **kwargs)


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

    try:
        download_url, version = get_latest_linux_bedrock_url()
        print(f"🎉 Latest version: {version}")
        print(f"🔗 Download URL: {download_url}")
        download_with_curl(download_url, output_zip)
    except Exception as e:
        print(f"❌ Error during Bedrock download: {e}")

    time.sleep(2)

    # Docker: logout → login → build/push → logout
    docker_logout()
    try:
        docker_login(username, pass_file=pass_file)
        docker_build_and_push(image)
    finally:
        docker_logout()

    # Git add/commit/push (if there are changes)
    try:
        git_add_commit_push()
    except subprocess.CalledProcessError as e:
        print(f"⚠️  Git step failed: {e}")


if __name__ == "__main__":
    main()
