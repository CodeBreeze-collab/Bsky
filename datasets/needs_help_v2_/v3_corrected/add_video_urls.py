import os
import json
import re
import time
import requests
from datetime import datetime

# Input and Output paths following your consolidated structure
INPUT_DIR = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/needs_help_v2_/v3_corrected" # "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/debug-src"  # "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/needs_help_v2_/v3/has_pledge"
OUTPUT_DIR = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/needs_help_v2_/v3_corrected/video_enriched_5" # "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/debug-out" # "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/needs_help_v2_/v3_corrected/video_enriched_4"

# Bluesky Public AppView Endpoints
BSKY_GET_POSTS = "https://public.api.bsky.app/xrpc/app.bsky.feed.getPosts"
BSKY_RESOLVE_HANDLE = "https://public.api.bsky.app/xrpc/com.atproto.identity.resolveHandle"

# Shared cache to prevent looking up the same handle thousands of times
HANDLE_TO_DID_CACHE = {}


def parse_date_dir(dirname):
    """Convert MM-DD-YYYY directory name to datetime."""
    try:
        return datetime.strptime(dirname, "%m-%d-%Y")
    except ValueError:
        return None


def get_sorted_date_dirs(input_dir):
    """Return date directories sorted newest -> oldest."""
    dirs = []
    if not os.path.exists(input_dir):
        return dirs
    for name in os.listdir(input_dir):
        path = os.path.join(input_dir, name)
        if os.path.isdir(path):
            dt = parse_date_dir(name)
            if dt:
                dirs.append((dt, path))
    dirs.sort(key=lambda x: x[0], reverse=True)
    return dirs


def extract_handle_and_rkey(url):
    """Extracts handle and record key (rkey) from a standard web URL."""
    if not url:
        return None, None
    match = re.search(r"https://bsky\.app/profile/([^/]+)/post/([^/]+)", url)
    if match:
        return match.groups()  # (handle, rkey)
    return None, None


def extract_rkey_from_uri(uri):
    """Extracts the rkey from an internal AT URI layout string."""
    if not uri:
        return None
    match = re.search(r"/app\.bsky\.feed\.post/([a-z0-9]+)", uri)
    return match.group(1) if match else None


def resolve_handle(handle):
    """Resolves a handle to its permanent DID with local caching."""
    if handle in HANDLE_TO_DID_CACHE:
        return HANDLE_TO_DID_CACHE[handle]

    try:
        resp = requests.get(BSKY_RESOLVE_HANDLE, params={"handle": handle}, timeout=5)
        if resp.status_code == 200:
            did = resp.json().get("did")
            if did:
                HANDLE_TO_DID_CACHE[handle] = did
                return did
    except Exception as e:
        print(f"  [Warning] Failed to resolve handle {handle}: {e}")

    return None


def fetch_video_urls(did_uris):
    """Queries Bluesky for an array of DID-based URIs and extracts playlist paths."""
    video_map = {}
    if not did_uris:
        return video_map

    try:
        response = requests.get(BSKY_GET_POSTS, params={"uris": did_uris}, timeout=10)
        if response.status_code == 200:
            data = response.json()
            for post in data.get("posts", []):
                uri = post.get("uri")
                rkey = extract_rkey_from_uri(uri)
                if not rkey:
                    continue

                embed = post.get("embed", {})

                # Check for standard video views
                if embed.get("$type") == "app.bsky.embed.video#view":
                    video_map[rkey] = embed.get("playlist", "")

                # Check for video attached inside quote posts
                elif embed.get("$type") == "app.bsky.embed.recordWithMedia#view":
                    media = embed.get("media", {})
                    if media.get("$type") == "app.bsky.embed.video#view":
                        video_map[rkey] = media.get("playlist", "")
    except Exception as e:
        print(f"  [Warning] Bluesky post query error: {e}")

    return video_map


def load_existing_records(output_file):
    existing = {}
    if not os.path.exists(output_file):
        return existing
    with open(output_file, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                key = record.get("animal_id") or record.get("post_url")
                if key:
                    existing[key] = record
            except json.JSONDecodeError:
                continue
    return existing


def process_file(input_file, output_file):
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    existing_records = load_existing_records(output_file)

    if existing_records:
        print(f"  Found {len(existing_records)} existing records, resuming...")

    # Load un-processed records into a work queue
    all_records = []
    skipped = 0
    with open(input_file, "r", encoding="utf-8") as infile:
        for line in infile:
            if not line.strip():
                continue
            record = json.loads(line)
            key = record.get("animal_id") or record.get("post_url")

            if key in existing_records:
                skipped += 1
                continue
            all_records.append(record)

    if not all_records:
        print(f"  Done: processed=0, skipped={skipped}, API batches=0")
        return

    processed_count = 0
    api_calls = 0
    batch_size = 25

    # Stream out data in real time, batch-by-batch
    with open(output_file, "a", encoding="utf-8") as outfile:
        for i in range(0, len(all_records), batch_size):
            batch_records = all_records[i:i + batch_size]

            rkey_to_indices = {}
            did_uris_to_fetch = []

            for idx, record in enumerate(batch_records):
                record["video_url"] = ""  # Default baseline initialization

                post_url = record.get("post_url") or (
                    record.get("associated_posts", [{}])[0].get("post_url")
                    if record.get("associated_posts") else None
                )

                handle, rkey = extract_handle_and_rkey(post_url)
                if handle and rkey:
                    # Dynamically convert handle to DID format
                    did = resolve_handle(handle)
                    if did:
                        did_uri = f"at://{did}/app.bsky.feed.post/{rkey}"

                        if rkey not in rkey_to_indices:
                            rkey_to_indices[rkey] = []
                        rkey_to_indices[rkey].append(idx)
                        did_uris_to_fetch.append(did_uri)

            # Fetch and extract if we built valid DID URIs
            if did_uris_to_fetch:
                api_calls += 1
                video_results = fetch_video_urls(did_uris_to_fetch)

                # Apply updates across this batch slice
                for rkey, video_url in video_results.items():
                    if rkey in rkey_to_indices:
                        for target_idx in rkey_to_indices[rkey]:
                            batch_records[target_idx]["video_url"] = video_url

                            # Also update the tracking records array if present
                            if batch_records[target_idx].get("associated_posts"):
                                for post in batch_records[target_idx]["associated_posts"]:
                                    _, post_rkey = extract_handle_and_rkey(post.get("post_url"))
                                    if post_rkey == rkey:
                                        post["video_url"] = video_url

            # Write out this batch to disk instantly
            for record in batch_records:
                outfile.write(json.dumps(record, ensure_ascii=False) + "\n")

            outfile.flush()  # Forces system to dump the write buffer out to the file system
            processed_count += len(batch_records)
            time.sleep(0.2)

    print(f"  Done: processed={processed_count}, skipped={skipped}, API calls={api_calls}")


def main():
    date_dirs = get_sorted_date_dirs(INPUT_DIR)
    if not date_dirs:
        print(f"No date directories found in {INPUT_DIR}")
        return

    for dt, date_dir in date_dirs:
        print(f"\nProcessing date directory: {dt.strftime('%m-%d-%Y')}")

        for root, _, files in os.walk(date_dir):
            for filename in files:
                if filename != "animal_centric_posts-w-loc-2.jsonl":
                    continue

                input_file = os.path.join(root, filename)
                relative = os.path.relpath(root, INPUT_DIR)
                output_file = os.path.join(OUTPUT_DIR, relative, filename)

                print(f"  {input_file}")
                process_file(input_file, output_file)


if __name__ == "__main__":
    main()