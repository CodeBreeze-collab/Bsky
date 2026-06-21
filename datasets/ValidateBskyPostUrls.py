import json
import requests
import sys
import re


def get_at_uri(url):
    """Converts a web URL (DID or Handle) to an AT Protocol URI."""
    # This pattern matches both did:plc:xyz and handle.bsky.social
    pattern = r"profile/([a-zA-Z0-9.:\-]+)/post/([a-z0-9]+)"
    match = re.search(pattern, url)

    if match:
        identifier, post_id = match.groups()
        # Bluesky API can usually resolve at://handle.bsky.social/...
        # just as well as at://did:plc:...
        return f"at://{identifier}/app.bsky.feed.post/{post_id}"
    return None


def check_post_exists(url):
    """Checks the Bluesky API to see if the post actually exists."""
    at_uri = get_at_uri(url)
    if not at_uri:
        return False, "Invalid URL format"

    # Public Bluesky API endpoint
    api_url = "https://public.api.bsky.app/xrpc/app.bsky.feed.getPostThread"
    params = {"uri": at_uri, "depth": 0}

    try:
        response = requests.get(api_url, params=params, timeout=10)

        if response.status_code == 200:
            return True, "Valid"
        elif response.status_code == 400:
            # The API returns 400 with 'NotFoundError' if the post is gone
            error_data = response.json()
            return False, error_data.get('error', 'Not Found')
        else:
            return False, f"API Error {response.status_code}"

    except Exception as e:
        return False, str(e)


def main(file_path):
    print(f"--- Validating via Bluesky API: {file_path} ---\n")

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip(): continue

                data = json.loads(line)
                url = data.get('post_url')

                exists, reason = check_post_exists(url)

                status = "✓ VALID" if exists else "✗ NOT FOUND"
                print(f"[{status}] {url} ({reason})")

    except FileNotFoundError:
        print(f"File '{file_path}' not found.")


if __name__ == "__main__":
    target_file = '/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/needs_help/03-11-2026/bluesky_rescue_posts_output-v8.jsonl'
    main(target_file)