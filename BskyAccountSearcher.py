from atproto import Client
from typing import List, Dict
from enum import Enum
import os
import json
from datetime import datetime
import time
import random

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

    import time
    import random

    def _fetch_accounts(self, target_handle: str, mode: str, limit: int):
        cursor = None
        results = []
        page = 0

        while len(results) < limit:

            remaining = limit - len(results)
            page_size = min(100, remaining)
            params = {"actor": target_handle, "limit": page_size, "cursor": cursor}

            try:
                if mode == "followers":
                    resp = self.client.app.bsky.graph.get_followers(params=params)
                    batch = resp.followers
                elif mode == "following":
                    resp = self.client.app.bsky.graph.get_follows(params=params)
                    batch = resp.follows
                else:
                    raise ValueError("mode must be 'followers' or 'following'")
            except Exception as e:
                print(f"Error fetching page {page + 1}: {e}")
                print("Retrying in 5 seconds...")
                time.sleep(5)
                continue  # retry same page

            page += 1
            results.extend(batch)

            # Print handles for sanity
            handles_in_page = [acct.handle for acct in batch]
            print(f"Page {page}: fetched {len(batch)} accounts (total collected: {len(results)})")
            print("Handles in this page:", ", ".join(handles_in_page))

            cursor = resp.cursor
            if not cursor:
                print("No more pages available.")
                break

            # --- Delay to avoid timeouts ---
            delay = random.uniform(0.5, 1.5)  # random 0.5–1.5 sec
            time.sleep(delay)

        print(f"Finished fetching. Total accounts processed: {len(results)}")
        return results


    def find_accounts_with_keywords(
        self,
        target_handle: str,
        keywords: List[str],
        mode: str = "following", #followers
        limit: int = 500,
        fields: List[SearchField] = None
    ) -> List[Dict]:

        if not self.client:
            return []

        if fields is None:
            fields = [
                SearchField.HANDLE,
                SearchField.DISPLAY_NAME,
                SearchField.DESCRIPTION
            ]

        accounts = self._fetch_accounts(target_handle, mode, limit)

        keywords = [k.lower() for k in keywords]
        matches = []

        for acct in accounts:

            values = {
                SearchField.HANDLE: acct.handle or "",
                SearchField.DISPLAY_NAME: acct.display_name or "",
                SearchField.DESCRIPTION: acct.description or ""
            }

            matched_keywords = set()

            for field in fields:

                text = values[field].lower()

                for kw in keywords:
                    if kw in text:
                        matched_keywords.add(kw)

            if matched_keywords:

                matches.append({
                    "handle": acct.handle,
                    "did": acct.did,
                    "display_name": acct.display_name,
                    "description": acct.description,
                    "matched_keywords": list(matched_keywords),
                    "source_account": target_handle
                })

        print(f"Matched {len(matches)} accounts")
        return matches


def load_existing_handles(jsonl_path: str) -> set:
    """
    Load existing handles from JSONL file to prevent duplicates.
    """

    handles = set()

    if not os.path.exists(jsonl_path):
        return handles

    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                record = json.loads(line)
                handles.add(record["handle"])
            except Exception:
                continue

    print(f"Loaded {len(handles)} existing handles")
    return handles


def append_to_jsonl(data: List[Dict], jsonl_path: str):

    existing_handles = load_existing_handles(jsonl_path)

    new_records = []

    for record in data:

        if record["handle"] in existing_handles:
            continue

        record["written_at"] = datetime.utcnow().isoformat() + "Z"

        new_records.append(record)
        existing_handles.add(record["handle"])

    if not new_records:
        print("No new accounts to write.")
        return

    os.makedirs(os.path.dirname(jsonl_path), exist_ok=True)

    with open(jsonl_path, "a", encoding="utf-8") as f:
        for r in new_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"Wrote {len(new_records)} new records to {jsonl_path}")


if __name__ == "__main__":

    HANDLE = "ethicalsearch.bsky.social"
    PASSWORD = os.environ.get("BLUESKY_APP_PASSWORD")

    # ✅ List of target accounts
    targets = [
        "oddpawsrescue.bsky.social",
    ]

    output_file = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/bluesky_rescue_accounts.jsonl"

    keywords = [
        "sanctuary",
        "rescue"
    ]

    searcher = BlueskyAccountSearcher(HANDLE, PASSWORD)

    for target in targets:
        print(f"\n=== Processing target: {target} ===")
        results = searcher.find_accounts_with_keywords(
            target_handle=target,
            keywords=keywords,
            mode="followers",   # or "following"
            limit=52000,
            fields=[
                SearchField.HANDLE,
                SearchField.DISPLAY_NAME,
                # SearchField.DESCRIPTION
            ]
        )

        append_to_jsonl(results, output_file)

        # Optional: small delay between targets
        time.sleep(random.uniform(1, 3))