import os
import json
import time
import re
from datetime import datetime
from pathlib import Path
from atproto import Client

# --- USER CONFIGURATION ---
HANDLES_FILE = "/Users/hdon/Desktop/over-30-days-no-follow.txt"
OUTPUT_DIR = "profile_audits"
# Define a FIXED filename if you want to resume the SAME audit,
# or the script will look for the most recent one in the folder.
RESUME_FILE = None  # Set to "profile_audits/audit_20260129_151445.jsonl" to target a specific file

KEYWORDS = ["vegan", "animal rights", "animal activism", "animal activist", " cat", " cats", " dog", " dogs"]
MY_HANDLE = "ethicalsearch.bsky.social"
APP_PASSWORD = os.getenv("BLUESKY_APP_PASSWORD")


def load_processed_handles(output_path):
    """Reads the JSONL and returns a set of handles already processed."""
    processed = set()
    if os.path.exists(output_path):
        with open(output_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    data = json.loads(line)
                    if "handle" in data:
                        processed.add(data["handle"].lower())
                except:
                    continue
    return processed


def get_keyword_stats(description, posts_text, keywords):
    found_keywords = set()
    posts_with_matches = 0
    for kw in keywords:
        clean_kw = kw.strip()
        pattern = rf"\b{re.escape(clean_kw)}\b"
        if description and re.search(pattern, description, re.IGNORECASE):
            found_keywords.add(clean_kw.lower())
    for post in posts_text:
        post_has_match = False
        for kw in keywords:
            clean_kw = kw.strip()
            if re.search(rf"\b{re.escape(clean_kw)}\b", post, re.IGNORECASE):
                found_keywords.add(clean_kw.lower())
                post_has_match = True
        if post_has_match:
            posts_with_matches += 1
    return sorted(list(found_keywords)), posts_with_matches


def main():
    if not APP_PASSWORD:
        print("❌ ERROR: BLUESKY_APP_PASSWORD not set.")
        return

    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    client = Client()
    client.login(MY_HANDLE, APP_PASSWORD)

    # Determine which file to write to
    if RESUME_FILE:
        full_output_path = RESUME_FILE
    else:
        # Create a new file for this session
        timestamp = datetime.now().strftime("%Y%m%d")
        full_output_path = os.path.join(OUTPUT_DIR, f"audit_{timestamp}.jsonl")

    # 1. Load progress
    processed_set = load_processed_handles(full_output_path)
    if processed_set:
        print(f"🔄 Resuming: Found {len(processed_set)} handles already processed in {full_output_path}")

    with open(HANDLES_FILE, "r") as f:
        all_handles = [line.strip().lstrip('@') for line in f if line.strip()]

    print(f"🚀 Scanning {len(all_handles)} total users.")

    with open(full_output_path, "a", encoding="utf-8") as out_file:
        for i, handle in enumerate(all_handles, 1):
            # 2. Skip logic
            if handle.lower() in processed_set:
                continue

            try:
                print(f"[{i}/{len(all_handles)}] 🔍 @{handle}...", end=" ", flush=True)
                profile = client.get_profile(actor=handle)
                feed = client.get_author_feed(actor=handle, limit=10)
                posts_text = [view.post.record.text for view in feed.feed]

                matches, post_match_count = get_keyword_stats(profile.description, posts_text, KEYWORDS)

                record = {
                    "matched_keywords": matches,
                    "posts_with_matches_count": post_match_count,
                    "handle": handle,
                    "profile_text": profile.description or "",
                    "scanned_at": datetime.now().isoformat()
                }

                out_file.write(json.dumps(record, ensure_ascii=False) + "\n")
                out_file.flush()
                os.fsync(out_file.fileno())

                print(f"✅ {matches} | {post_match_count}/10")

            except Exception as e:
                print(f"❌ Skip: {e}")

            time.sleep(1.2)

    print(f"\n✨ Audit complete. Results: {full_output_path}")


if __name__ == "__main__":
    main()