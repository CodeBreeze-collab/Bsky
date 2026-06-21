import os
import json
import time
import random
from datetime import datetime
from enum import Enum
from typing import List, Dict
from atproto import Client


class SearchField(Enum):
    HANDLE = "handle"
    DISPLAY_NAME = "display_name"
    DESCRIPTION = "description"


class BlueskyAccountSearcher:
    def __init__(self, handle: str, password: str):
        self.client = Client()
        try:
            self.client.login(handle, password)
            print(f"Logged in as {handle}")
        except Exception as e:
            print(f"Login failed: {e}")
            self.client = None

    def find_accounts_with_keywords(
            self,
            target_handle: str,
            keywords: List[str],
            output_file: str,
            mode: str = "followers",
            limit: int = 500,
            fields: List[SearchField] = None
    ):
        if not self.client:
            print("Client not initialized.")
            return

        # Explicitly setting only Handle and Display Name to avoid the previous error
        if fields is None:
            fields = [SearchField.HANDLE, SearchField.DISPLAY_NAME]

        keywords = [k.lower() for k in keywords]
        existing_handles = load_existing_handles(output_file)

        cursor = None
        total_fetched = 0
        matches_found = 0

        while total_fetched < limit:
            remaining = limit - total_fetched
            page_size = min(100, remaining)
            params = {"actor": target_handle, "limit": page_size, "cursor": cursor}

            try:
                if mode == "followers":
                    resp = self.client.app.bsky.graph.get_followers(params=params)
                    batch = resp.followers
                else:
                    resp = self.client.app.bsky.graph.get_follows(params=params)
                    batch = resp.follows

                if not batch:
                    break

                current_page_matches = []
                for acct in batch:
                    # Logic: Create mapping only for fields we actually want to check
                    values = {
                        SearchField.HANDLE: (acct.handle or "").lower(),
                        SearchField.DISPLAY_NAME: (acct.display_name or "").lower()
                    }

                    matched_kws = set()
                    for field in fields:
                        if field in values:  # Extra safety check
                            text = values[field]
                            for kw in keywords:
                                if kw in text:
                                    matched_kws.add(kw)

                    if matched_kws and acct.handle not in existing_handles:
                        record = {
                            "handle": acct.handle,
                            "did": acct.did,
                            "display_name": acct.display_name,
                            "description": acct.description,
                            "matched_keywords": list(matched_kws),
                            "source_account": target_handle,
                            "written_at": datetime.utcnow().isoformat() + "Z"
                        }
                        current_page_matches.append(record)
                        existing_handles.add(acct.handle)

                if current_page_matches:
                    os.makedirs(os.path.dirname(output_file), exist_ok=True)
                    with open(output_file, "a", encoding="utf-8") as f:
                        for r in current_page_matches:
                            f.write(json.dumps(r, ensure_ascii=False) + "\n")
                    matches_found += len(current_page_matches)
                    print(f"  [MATCHED] Saved {len(current_page_matches)} accounts from {target_handle}.")

                total_fetched += len(batch)
                cursor = resp.cursor
                if not cursor: break
                time.sleep(random.uniform(0.5, 1.1))

            except Exception as e:
                print(f"Error during fetch: {e}")
                time.sleep(5)
                continue

        return matches_found


# -------------------- HELPERS --------------------

def load_existing_handles(jsonl_path: str) -> set:
    handles = set()
    if not os.path.exists(jsonl_path): return handles
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                record = json.loads(line)
                handles.add(record["handle"])
            except:
                continue
    return handles


def get_unused_source_targets(jsonl_path: str) -> List[str]:
    all_found_handles = set()
    used_as_source = set()
    if not os.path.exists(jsonl_path): return []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                record = json.loads(line)
                if record.get("handle"): all_found_handles.add(record["handle"])
                if record.get("source_account"): used_as_source.add(record["source_account"])
            except:
                continue
    return list(all_found_handles - used_as_source)


# -------------------- NEW WORKFLOW FUNCTIONS --------------------

def run_single_target(searcher, target_handle, keywords, output_file, limit=5000):
    """Function to extract from exactly one handle and stop."""
    print(f"\n--- Running Single Target: {target_handle} ---")
    count = searcher.find_accounts_with_keywords(
        target_handle=target_handle,
        keywords=keywords,
        output_file=output_file,
        limit=limit
    )
    print(f"Done. Found {count} matches.")


def run_as_crawl(searcher, keywords, output_file, limit_per_target=5000):
    """Function to perform the recursive crawl based on existing file data."""
    print("\n--- Starting Recursive Crawl ---")
    targets = get_unused_source_targets(output_file)

    if not targets:
        print("No new targets found in the dataset to use as seeds.")
        return

    print(f"Found {len(targets)} new seeds to explore.")
    random.shuffle(targets)

    for target in targets:
        print(f"\n>>> Crawling Seed: {target}")
        searcher.find_accounts_with_keywords(
            target_handle=target,
            keywords=keywords,
            output_file=output_file,
            limit=limit_per_target
        )
        time.sleep(random.uniform(3, 6))


# -------------------- MAIN --------------------

if __name__ == "__main__":
    B_HANDLE = "ethicalsearch.bsky.social"
    B_PASS = os.environ.get("BLUESKY_APP_PASSWORD")

    FILE_PATH = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/bluesky_rescue_accounts-03-12-2026-handle-title.jsonl"
    KWS = ["sanctuary", "rescue"]

    searcher = BlueskyAccountSearcher(B_HANDLE, B_PASS)
    if searcher.client:
        # CHOICE 1: Run one specific person to "seed" the file
        # run_single_target(searcher, "youngatheartpets.bsky.social", KWS, FILE_PATH)

        # CHOICE 2: Run the automated crawl
        run_as_crawl(searcher, KWS, FILE_PATH)