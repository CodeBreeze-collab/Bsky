from atproto import Client
import os
import time
import random
import json
from pathlib import Path
import re

# --- Configuration ---
HANDLE = "vegansearchengine.bsky.social"
APP_PASSWORD = os.getenv("BLUESKY_APP_PASSWORD")
KEYWORDS = ["porn", "onlyfans", "adult", "nsfw"]  # Keywords to flag
FLAGGED_OUTPUT = "flagged_followers.jsonl"
CLEAN_OUTPUT = "clean_followers.jsonl"
MIN_DELAY = 0.8  # seconds
MAX_DELAY = 2.0  # seconds


def keyword_match(bio: str, keywords: list) -> list:
    """
    Return a list of keywords matched in the bio, ignoring negations like 'no porn'.
    Case-insensitive.
    """
    if not bio:
        return []

    bio_lower = bio.lower()
    matches = []

    for kw in keywords:
        # Pattern matches keyword NOT preceded by 'no ' (with optional spaces)
        pattern = rf"(?<!\bno\s){re.escape(kw.lower())}"
        if re.search(pattern, bio_lower):
            matches.append(kw)

    return matches


def load_existing(file_path: str) -> set:
    """Load handles and DIDs from a JSONL file into a set for skipping already-checked accounts."""
    existing = set()
    path = Path(file_path)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    data = json.loads(line)
                    existing.add(data.get("handle"))
                    existing.add(data.get("did"))
                except:
                    continue
    return existing


def main():
    if not APP_PASSWORD:
        print("❌ Environment variable BLUESKY_APP_PASSWORD not set.")
        return

    client = Client()
    client.login(HANDLE, APP_PASSWORD)
    print(f"Logged in as {HANDLE}. Fetching all followers...")

    flagged_count = 0
    clean_count = 0
    total_checked = 0
    cursor = None

    # Load existing accounts to skip
    seen_accounts = load_existing(FLAGGED_OUTPUT).union(load_existing(CLEAN_OUTPUT))

    # Open output files in append mode so we write results as they are processed
    with open(FLAGGED_OUTPUT, "a", encoding="utf-8") as flagged_file, \
         open(CLEAN_OUTPUT, "a", encoding="utf-8") as clean_file:

        while True:
            followers_response = client.get_followers(actor=HANDLE, cursor=cursor)
            followers = followers_response.followers

            if not followers:
                break  # No more followers

            for user in followers:
                # Skip accounts already processed
                if user.handle in seen_accounts or user.did in seen_accounts:
                    print(f"⚡ Skipping {user.handle}, already checked.")
                    continue

                total_checked += 1

                # Fetch profile
                profile = client.get_profile(actor=user.did)
                bio = profile.description or ""

                matched_keywords = keyword_match(bio, KEYWORDS)
                record = {
                    "handle": user.handle,
                    "did": user.did,
                    "bio": bio
                }

                if matched_keywords:
                    record["matched_keywords"] = matched_keywords
                    flagged_count += 1
                    print(f"⚠️ Follower {user.handle} flagged: {matched_keywords}")
                    # Write flagged record **immediately**
                    flagged_file.write(json.dumps(record, ensure_ascii=False) + "\n")
                    flagged_file.flush()
                else:
                    clean_count += 1
                    print(f"✅ Follower {user.handle} is clean.")
                    # Write clean record **immediately**
                    clean_file.write(json.dumps(record, ensure_ascii=False) + "\n")
                    clean_file.flush()

                # Add to seen to prevent duplicate processing in this run
                seen_accounts.add(user.handle)
                seen_accounts.add(user.did)

                # Random delay to respect API rate limits
                time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))

            # Pagination
            cursor = getattr(followers_response, "cursor", None)
            if not cursor:
                break

    print(f"\nFinished! Checked {total_checked} followers.")
    print(f"Flagged: {flagged_count}, Clean: {clean_count}")
    print(f"Flagged saved to {FLAGGED_OUTPUT}, Clean saved to {CLEAN_OUTPUT}")


if __name__ == "__main__":
    main()
