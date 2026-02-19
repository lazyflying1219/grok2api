"""Debug script: fetch sign-up page and analyze JS bundles for payload format."""
import re
import sys
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests

SITE_URL = "https://accounts.x.ai"


def main():
    with curl_requests.Session(impersonate="chrome120") as session:
        print("=== Fetching sign-up page ===")
        res = session.get(f"{SITE_URL}/sign-up", timeout=15)
        print(f"Status: {res.status_code}")
        html = res.text

        # Extract sitekey
        key_match = re.search(r'sitekey":"(0x4[a-zA-Z0-9_-]+)"', html)
        print(f"Sitekey: {key_match.group(1) if key_match else 'NOT FOUND'}")

        # Extract state tree
        tree_match = re.search(r'next-router-state-tree":"([^"]+)"', html)
        print(f"State tree: {tree_match.group(1)[:80] + '...' if tree_match else 'NOT FOUND'}")

        # Find JS bundles
        soup = BeautifulSoup(html, "html.parser")
        js_urls = [
            urljoin(f"{SITE_URL}/sign-up", script["src"])
            for script in soup.find_all("script", src=True)
            if "_next/static" in script["src"]
        ]
        print(f"\nFound {len(js_urls)} JS bundles")

        # Search for action_id pattern and surrounding context
        for js_url in js_urls:
            js_content = session.get(js_url, timeout=15).text
            matches = list(re.finditer(r"7f[a-fA-F0-9]{40}", js_content))
            if not matches:
                continue

            for match in matches:
                action_id = match.group(0)
                start = max(0, match.start() - 300)
                end = min(len(js_content), match.end() + 300)
                context = js_content[start:end]
                print(f"\n=== Action ID: {action_id} ===")
                print(f"JS URL: {js_url}")
                print(f"Context ({start}-{end}):")
                print(context)
                print("=" * 60)

        # Also search for tosAcceptedVersion, createUserAndSession, emailValidationCode
        print("\n=== Searching for payload field names ===")
        for js_url in js_urls:
            js_content = session.get(js_url, timeout=15).text
            for keyword in [
                "tosAcceptedVersion",
                "createUserAndSession",
                "emailValidationCode",
                "turnstileToken",
                "clearTextPassword",
                "promptOnDuplicate",
                "signUp",
            ]:
                positions = [m.start() for m in re.finditer(keyword, js_content)]
                if positions:
                    print(f"\n--- '{keyword}' found in {js_url.split('/')[-1]} at {len(positions)} position(s) ---")
                    for pos in positions[:3]:
                        start = max(0, pos - 150)
                        end = min(len(js_content), pos + 150)
                        print(f"  [{pos}]: ...{js_content[start:end]}...")


if __name__ == "__main__":
    main()
