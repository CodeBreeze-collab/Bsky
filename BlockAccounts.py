import os
import json
import time
import argparse
from atproto import Client

CONFIG_PATH = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/all-in-one-configs/account_creds.json"
BLOCKLIST_PATH = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/v2/nes_blocks.txt"
# "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/block_list/vs_search_blocks.txt"  # now a simple newline-separated DID file


def load_config(path):
    with open(path, "r") as f:
        return json.load(f)


def load_blocklist(path):
    dids = []
    with open(path, "r") as f:
        for line in f:
            did = line.strip()
            if did:
                dids.append(did)
    return dids


def resolve_did_to_handle(client, did, cache):
    if did in cache:
        return cache[did]

    try:
        resp = client.app.bsky.actor.get_profile({"actor": did})
        handle = resp.handle
    except Exception:
        handle = None

    cache[did] = handle
    return handle


def block_user(client, did):
    client.app.bsky.graph.block.create(
        repo=client.me.did,
        record={
            "subject": did,
            "createdAt": client.get_current_time_iso(),
        },
    )


def list_blocks(client, resolve_handles=False, rate_delay=0.5):
    cursor = None
    cache = {}

    print("\nFetching blocks...")

    while True:
        try:
            resp = client.app.bsky.graph.get_blocks(
                {"limit": 100, "cursor": cursor} if cursor else {"limit": 100}
            )
        except Exception as e:
            print(f"[ERROR] Failed to fetch blocks: {e}")
            return

        blocks = resp.blocks or []
        if not blocks:
            break

        for block in blocks:
            did = block.did  # FIXED: attribute access

            if resolve_handles:
                handle = resolve_did_to_handle(client, did, cache)
                print(f"{handle or 'UNKNOWN'} ({did})")
                time.sleep(rate_delay)
            else:
                print(did)

        cursor = resp.cursor
        if not cursor:
            break


def run_blocking(accounts, dids, rate_delay):
    for acct in accounts:
        handle = acct.get("handle")
        env_var = acct.get("env_var")

        password = os.getenv(env_var)
        if not password:
            print(f"Missing env var for {handle}: {env_var}")
            continue

        print(f"\nLogging in as {handle}")
        client = Client()

        try:
            client.login(handle, password)
        except Exception as e:
            print(f"[LOGIN FAILED] {handle}: {e}")
            continue

        # --- Added Logic: Fetch existing blocks to avoid duplicates ---
        existing_blocks = set()
        cursor = None
        while True:
            resp = client.app.bsky.graph.get_blocks(
                {"limit": 100, "cursor": cursor} if cursor else {"limit": 100}
            )
            for b in resp.blocks:
                existing_blocks.add(b.did)
            cursor = resp.cursor
            if not cursor:
                break
        # -----------------------------------------------------------

        for did in dids:
            if did in existing_blocks:
                print(f"Skipping {did}: Already blocked.")
                continue

            try:
                block_user(client, did)
                print(f"Blocked {did}")
                time.sleep(rate_delay)
            except Exception as e:
                print(f"Failed for {did}: {e}")


def run_list_blocks(accounts, resolve_handles, rate_delay):
    for acct in accounts:
        handle = acct.get("handle")
        env_var = acct.get("env_var")

        password = os.getenv(env_var)
        if not password:
            print(f"Missing env var for {handle}: {env_var}")
            continue

        print(f"\n=== Blocks for {handle} ===")
        client = Client()

        try:
            client.login(handle, password)
        except Exception as e:
            print(f"[LOGIN FAILED] {handle}: {e}")
            continue

        list_blocks(client, resolve_handles=resolve_handles, rate_delay=rate_delay)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--list-blocks", action="store_true")
    parser.add_argument("--resolve-handles", action="store_true")
    args = parser.parse_args()

    config = load_config(CONFIG_PATH)
    accounts = config.get("accounts", [])
    rate_delay = config.get("rate_delay", 1.0)

    if args.list_blocks:
        run_list_blocks(accounts, args.resolve_handles, rate_delay)
    else:
        dids = load_blocklist(BLOCKLIST_PATH)
        run_blocking(accounts, dids, rate_delay)


if __name__ == "__main__":
    main()