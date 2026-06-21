import requests
from urllib.parse import urlparse
import time
import argparse
import sys

BASE = "https://bsky.social/xrpc"


# ---------- AUTH ----------
def create_session(username, password):
    try:
        res = requests.post(
            f"{BASE}/com.atproto.server.createSession",
            json={"identifier": username, "password": password}
        )
        res.raise_for_status()
        return res.json()["accessJwt"], res.json()["did"]
    except Exception as e:
        print(f"Authentication failed: {e}")
        sys.exit(1)


# ---------- RESOLVE ----------
def resolve_handle(handle):
    if handle.startswith("did:"):
        return handle
    res = requests.get(
        "https://public.api.bsky.app/xrpc/com.atproto.identity.resolveHandle",
        params={"handle": handle}
    )
    res.raise_for_status()
    return res.json()["did"]


def url_to_at_uri(post_url):
    try:
        parts = urlparse(post_url).path.split("/")
        # Expected path: /profile/{handle}/post/{id}
        handle_or_did = parts[2]
        post_id = parts[4]
        did = handle_or_did if handle_or_did.startswith("did:") else resolve_handle(handle_or_did)
        return f"at://{did}/app.bsky.feed.post/{post_id}"
    except Exception as e:
        print(f"Error parsing URL: {e}")
        sys.exit(1)


# ---------- GET LIKES ----------
def get_likes(uri):
    likes = []
    cursor = None
    while True:
        params = {"uri": uri, "limit": 100}
        if cursor: params["cursor"] = cursor
        res = requests.get("https://public.api.bsky.app/xrpc/app.bsky.feed.getLikes", params=params)
        res.raise_for_status()
        data = res.json()
        for like in data.get("likes", []):
            likes.append(like["actor"]["did"])
        cursor = data.get("cursor")
        if not cursor: break
    return set(likes)


# ---------- BLOCK ----------
def block_user(did_to_block, token, my_did):
    headers = {"Authorization": f"Bearer {token}"}
    record = {
        "$type": "app.bsky.graph.block",
        "subject": did_to_block,
        "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ")
    }
    res = requests.post(
        f"{BASE}/com.atproto.repo.createRecord",
        headers=headers,
        json={"repo": my_did, "collection": "app.bsky.graph.block", "record": record}
    )
    return res.status_code == 200


# ---------- MONITORING LOOP ----------
def monitor_and_block(args):
    print(f"Starting monitor for: {args.url}")
    token, my_did = create_session(args.username, args.password)
    uri = url_to_at_uri(args.url)

    blocked_dids = set()

    while True:
        try:
            print(f"\nChecking for new likes... ({time.strftime('%H:%M:%S')})")
            current_likers = get_likes(uri)
            new_to_block = current_likers - blocked_dids

            if not new_to_block:
                print("No new likers found.")
            else:
                print(f"Found {len(new_to_block)} new users to block.")
                for did in new_to_block:
                    if block_user(did, token, my_did):
                        print(f"Successfully blocked: {did}")
                        blocked_dids.add(did)
                    time.sleep(1)

        except Exception as e:
            print(f"An error occurred: {e}")
            # Attempt to re-auth in case of token expiry
            try:
                token, my_did = create_session(args.username, args.password)
            except:
                pass

        print(f"Waiting {args.interval} seconds until next check...")
        time.sleep(args.interval)


# ---------- CLI CONFIG ----------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Periodically block all users who like a specific Bluesky post.")

    # Required arguments
    parser.add_argument("--url", required=True, help="The full URL of the Bluesky post")
    parser.add_argument("--username", required=True, help="Your Bluesky handle (e.g., user.bsky.social)")
    parser.add_argument("--password", required=True, help="Your Bluesky App Password")

    # Optional arguments
    parser.add_argument("--interval", type=int, default=300, help="Seconds between checks (default: 300)")

    args = parser.parse_args()
    monitor_and_block(args)