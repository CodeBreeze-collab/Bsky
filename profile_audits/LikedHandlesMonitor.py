import requests
from urllib.parse import urlparse
import time
import argparse
import sys
from datetime import datetime, timezone

BASE = "https://bsky.social/xrpc"


# ---------- AUTH ----------
def create_session(username, password):
    try:
        res = requests.post(
            f"{BASE}/com.atproto.server.createSession",
            json={"identifier": username, "password": password}
        )
        res.raise_for_status()
        data = res.json()
        return data["accessJwt"], data["did"]
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
    """Returns a tuple of (post_uri, target_account_did)"""
    try:
        parts = urlparse(post_url).path.split("/")
        handle_or_did = parts[2]
        post_id = parts[4]
        did = handle_or_did if handle_or_did.startswith("did:") else resolve_handle(handle_or_did)
        return f"at://{did}/app.bsky.feed.post/{post_id}", did
    except Exception as e:
        print(f"Error parsing URL: {e}")
        sys.exit(1)


# ---------- GET LIKES WITH TIMESTAMPS ----------
def get_likes_data(uri):
    """Fetches likes returning a list of dicts with 'did' and 'createdAt'"""
    likes_data = []
    cursor = None

    while True:
        params = {"uri": uri, "limit": 100}
        if cursor:
            params["cursor"] = cursor
        try:
            res = requests.get(
                "https://public.api.bsky.app/xrpc/app.bsky.feed.getLikes",
                params=params
            )
            res.raise_for_status()
            data = res.json()

            for like in data.get("likes", []):
                likes_data.append({
                    "did": like["actor"]["did"],
                    "createdAt": like["createdAt"]
                })

            cursor = data.get("cursor")
            if not cursor:
                break
        except Exception as e:
            print(f"Warning: Interrupted while fetching likes pagination: {e}")
            break

    return likes_data


# ---------- CHECK RELATIONSHIP ----------
def check_relationship(target_did, liker_did, token):
    """Checks if target account follows the liker OR if the liker follows target account"""
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "actor": target_did,
        "others": [liker_did]
    }
    try:
        res = requests.get(
            f"{BASE}/app.bsky.graph.getRelationships",
            headers=headers,
            params=params
        )
        res.raise_for_status()
        data = res.json()

        relationships = data.get("relationships", [])
        if relationships:
            rel = relationships[0]
            # Ensure it's a valid relationship blueprint and not an unresolvable actor
            if rel.get("$type") == "app.bsky.graph.defs#relationship":
                is_following = "following" in rel and rel["following"] is not None
                is_followed_by = "followedBy" in rel and rel["followedBy"] is not None
                return is_following or is_followed_by
    except Exception as e:
        print(f"Warning: Failed to verify relationship for {liker_did}: {e}")

    return False


# ---------- BLOCK ----------
def block_user(did_to_block, token, my_did):
    headers = {"Authorization": f"Bearer {token}"}
    record = {
        "$type": "app.bsky.graph.block",
        "subject": did_to_block,
        "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ")
    }
    try:
        res = requests.post(
            f"{BASE}/com.atproto.repo.createRecord",
            headers=headers,
            json={
                "repo": my_did,
                "collection": "app.bsky.graph.block",
                "record": record
            }
        )
        return res.status_code == 200
    except:
        return False


# ---------- MONITOR ----------
def monitor_and_block(args):
    start_time_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    print(f"Script starting at (UTC): {start_time_str}")
    print(f"Monitoring: {args.url}")

    token, my_did = create_session(args.username, args.password)
    uri, target_did = url_to_at_uri(args.url)  # Unpacks both values now

    processed_likers = set()

    while True:
        try:
            print(f"\nChecking for new likes... ({time.strftime('%H:%M:%S')})")
            raw_likes = get_likes_data(uri)

            for item in raw_likes:
                did = item["did"]
                created_at = item["createdAt"]

                if did in processed_likers:
                    continue

                if args.only_future_likes:
                    if created_at < start_time_str:
                        processed_likers.add(did)
                        continue

                # WHITELIST CHECK: Protect network connections from friendly fire
                if check_relationship(target_did, did, token):
                    print(f"Skipping {did}: Has an active follow relationship with the target account.")
                    processed_likers.add(did)
                    continue

                # If it passes all safety rules, block them
                print(f"New like detected (Time: {created_at}). Blocking {did}...")
                if block_user(did, token, my_did):
                    print(f"Successfully blocked: {did}")

                processed_likers.add(did)
                time.sleep(1)

        except Exception as e:
            print(f"Loop error: {e}")
            try:
                token, my_did = create_session(args.username, args.password)
            except:
                pass

        time.sleep(args.interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Block users who like a Bluesky post")
    parser.add_argument("--url", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--interval", type=int, default=300)
    parser.add_argument("--only-future-likes", action="store_true")

    args = parser.parse_args()
    monitor_and_block(args)