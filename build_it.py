#! /usr/bin/python3

import requests
import subprocess

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
        "curl", "-i", "-s", "-k", "-X", "GET",
        "-H", "Host: www.minecraft.net",
        "-H", 'Sec-Ch-Ua: "Not:A-Brand";v="99", "Chromium";v="112"',
        "-H", "Sec-Ch-Ua-Mobile: ?0",
        '-H', 'Sec-Ch-Ua-Platform: "Windows"',
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
    subprocess.run(curl_cmd, check=True)
    print(f"✅ Downloaded to {output_file}")

def main():
    try:
        download_url, version = get_latest_linux_bedrock_url()
        print(f"🎉 Latest version: {version}")
        print(f"🔗 Download URL: {download_url}")
        download_with_curl(download_url, "bedrock-server.zip")
    except Exception as e:
        print(f"❌ Error: {e}")

    # Now I have the latest version
    subprocess.run(["sh", "build_it.sh"], check=True)


if __name__ == "__main__":
    main()
