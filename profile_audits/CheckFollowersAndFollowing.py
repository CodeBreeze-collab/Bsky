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
KEYWORDS = ["porn", "onlyfans", "nsfw", "hunting", "fishing"]

# SET YOUR MODES HERE
MODES = ["following"] # "followers",

MIN_DELAY = 1.0  # Slightly higher for stability
MAX_DELAY = 2.0


def keyword_match(bio: str, keywords: list) -> list:
    if not bio: return []
    bio_lower = bio.lower()
    matches = []
    for kw in keywords:
        pattern = rf"(?<!\bno\s){re.escape(kw.lower())}"
        if re.search(pattern, bio_lower):
            matches.append(kw)
    return matches


def load_existing(file_paths: list) -> set:
    """Reads existing JSONL files to build a set of already processed IDs."""
    existing = set()
    for file_path in file_paths:
        path = Path(file_path)
        if path.exists():
            print(f"📖 Loading existing data from {file_path}...")
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        data = json.loads(line)
                        if data.get("did"):
                            existing.add(data["did"])
                    except:
                        continue
    return existing


def process_accounts(client, mode):
    print(f"\n🚀 STARTING SCAN: {mode.upper()}")

    flagged_path = f"flagged_{mode}.jsonl"
    clean_path = f"clean_{mode}.jsonl"

    # CRITICAL FOR RESTARTING: Load seen IDs so we don't re-process or double-write
    seen_dids = load_existing([flagged_path, clean_path])
    print(f"✅ Found {len(seen_dids)} accounts already processed. Skipping these.")

    cursor = None
    counts = {"flagged": 0, "clean": 0, "skipped": 0}

    with open(flagged_path, "a", encoding="utf-8") as f_file, \
            open(clean_path, "a", encoding="utf-8") as c_file:

        while True:
            try:
                if mode == "followers":
                    response = client.get_followers(actor=HANDLE, cursor=cursor)
                    users = response.followers
                else:
                    response = client.get_follows(actor=HANDLE, cursor=cursor)
                    users = response.follows

                if not users:
                    break

                # Filter batch to only include users we HAVEN'T seen yet
                new_users = [u for u in users if u.did not in seen_dids]
                counts["skipped"] += (len(users) - len(new_users))

                # Process in batches of 25 (get_profiles limit)
                for i in range(0, len(new_users), 25):
                    batch = new_users[i: i + 25]
                    batch_dids = [u.did for u in batch]

                    profiles_response = client.get_profiles(actors=batch_dids)

                    for profile in profiles_response.profiles:
                        bio = profile.description or ""
                        matched = keyword_match(bio, KEYWORDS)

                        record = {
                            "handle": profile.handle,
                            "did": profile.did,
                            "bio": bio,
                            "display_name": profile.display_name
                        }

                        if matched:
                            record["matched_keywords"] = matched
                            counts["flagged"] += 1
                            print(f"⚠️ Flagged: {profile.handle}")
                            f_file.write(json.dumps(record, ensure_ascii=False) + "\n")
                        else:
                            counts["clean"] += 1
                            print(f"✅ Clean: {profile.handle}")
                            c_file.write(json.dumps(record, ensure_ascii=False) + "\n")

                        seen_dids.add(profile.did)

                    # Immediate save to disk
                    f_file.flush()
                    c_file.flush()
                    time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))

                cursor = getattr(response, "cursor", None)
                if not cursor:
                    break

            except Exception as e:
                print(f"⚠️ Connection error or rate limit: {e}. Sleeping 30s...")
                time.sleep(30)
                continue

    print(f"🏁 Finished {mode}! Flagged: {counts['flagged']}, Clean: {counts['clean']} (Skipped: {counts['skipped']})")


def main():
    if not APP_PASSWORD:
        print("❌ Error: BLUESKY_APP_PASSWORD not found in environment.")
        return

    client = Client()
    client.login(HANDLE, APP_PASSWORD)

    for mode in MODES:
        process_accounts(client, mode)


if __name__ == "__main__":
    main()