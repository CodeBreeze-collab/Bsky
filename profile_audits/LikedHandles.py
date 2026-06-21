import argparse
import os
import requests
from urllib.parse import urlparse
import time

BASE = "https://bsky.social/xrpc"  # authenticated endpoint

# It's recommended to set these via environment variables or keep them here securely
USERNAME = "vegansearchengine.bsky.social"
APP_PASSWORD = "px6u-e35r-ryay-qkxs"


# ---------- AUTH ----------
def create_session():
    if not APP_PASSWORD:
        raise ValueError("Please provide an APP_PASSWORD before running the script.")

    res = requests.post(
        f"{BASE}/com.atproto.server.createSession",
        json={
            "identifier": USERNAME,
            "password": APP_PASSWORD
        }
    )
    res.raise_for_status()
    return res.json()["accessJwt"], res.json()["did"]


# ---------- RESOLVE ----------
def resolve_handle(handle):
    if handle.startswith("did:"):
        return handle  # already a DID

    res = requests.get(
        "https://public.api.bsky.app/xrpc/com.atproto.identity.resolveHandle",
        params={"handle": handle}
    )
    res.raise_for_status()
    return res.json()["did"]


def url_to_at_uri(post_url):
    parts = urlparse(post_url).path.split("/")

    handle_or_did = parts[2]
    post_id = parts[4]

    if handle_or_did.startswith("did:"):
        did = handle_or_did
    else:
        did = resolve_handle(handle_or_did)

    return f"at://{did}/app.bsky.feed.post/{post_id}"


# ---------- GET LIKES ----------
def get_likes(uri):
    likes = []
    cursor = None

    while True:
        params = {"uri": uri, "limit": 100}
        if cursor:
            params["cursor"] = cursor

        res = requests.get(
            "https://public.api.bsky.app/xrpc/app.bsky.feed.getLikes",
            params=params
        )
        res.raise_for_status()
        data = res.json()

        for like in data.get("likes", []):
            likes.append(like["actor"]["did"])

        cursor = data.get("cursor")
        if not cursor:
            break

    return list(set(likes))  # dedupe


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
        json={
            "repo": my_did,
            "collection": "app.bsky.graph.block",
            "record": record
        }
    )

    if res.status_code != 200:
        print(f"Failed to block {did_to_block}: {res.text}")
    else:
        print(f"Blocked {did_to_block}")


# ---------- UNBLOCK ----------
def get_block_uri(target_did, token, my_did):
    """Finds the record URI for an existing block on a specific user."""
    headers = {"Authorization": f"Bearer {token}"}
    cursor = None

    while True:
        params = {"repo": my_did, "collection": "app.bsky.graph.block", "limit": 100}
        if cursor:
            params["cursor"] = cursor

        res = requests.get(
            f"{BASE}/com.atproto.repo.listRecords",
            headers=headers,
            params=params
        )
        res.raise_for_status()
        data = res.json()

        for record in data.get("records", []):
            if record.get("value", {}).get("subject") == target_did:
                return record["uri"]

        cursor = data.get("cursor")
        if not cursor:
            break

    return None


def unblock_user(did_to_unblock, token, my_did):
    headers = {"Authorization": f"Bearer {token}"}

    block_uri = get_block_uri(did_to_unblock, token, my_did)
    if not block_uri:
        print(f"No active block record found for {did_to_unblock}")
        return

    # Extract the rkey (record key) from the end of the AT URI
    rkey = block_uri.split("/")[-1]

    res = requests.post(
        f"{BASE}/com.atproto.repo.deleteRecord",
        headers=headers,
        json={
            "repo": my_did,
            "collection": "app.bsky.graph.block",
            "rkey": rkey
        }
    )

    if res.status_code != 200:
        print(f"Failed to unblock {did_to_unblock}: {res.text}")
    else:
        print(f"Unblocked {did_to_unblock}")


# ---------- PROCESS PROCESSOR ----------
def process_likers(post_url, undo_blocks=False):
    token, my_did = create_session()
    uri = url_to_at_uri(post_url)

    dids = get_likes(uri)
    action_text = "unblock" if undo_blocks else "block"
    print(f"Found {len(dids)} users to {action_text}")

    for did in dids:
        if undo_blocks:
            unblock_user(did, token, my_did)
        else:
            block_user(did, token, my_did)
        time.sleep(0.5)  # avoid rate limits



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Block or unblock everyone who liked a specific Bluesky post.")
    parser.path = parser.add_argument(
        "url",
        type=str,
        help="The full URL of the Bluesky post"
    )
    parser.add_argument(
        "--unblock",
        action="store_true",
        help="Pass this flag to unblock the users instead of blocking them"
    )

    args = parser.parse_args()

    process_likers(args.url, undo_blocks=args.unblock)