import json
import os
import argparse
from datetime import datetime
from atproto import Client

# --- CONFIGURATION ---
HANDLE = 'ethicalsearch.bsky.social'


def main():
    parser = argparse.ArgumentParser(description="Fetch Bluesky profile data with restart support.")
    parser.add_argument("input", help="Path to the input .json or .jsonl file")
    parser.add_argument("--output", help="Optional: Path to output .jsonl file")
    args = parser.parse_args()

    input_path = args.input
    if args.output:
        output_path = args.output
    else:
        base, _ = os.path.splitext(input_path)
        output_path = f"{base}_following_profiles.jsonl"

    password = os.environ.get('BLUESKY_APP_PASSWORD')
    if not password:
        print("Error: BLUESKY_APP_PASSWORD environment variable not set.")
        return

    # 1. Check for existing progress
    processed_dids = set()
    if os.path.exists(output_path):
        print(f"Found existing output file. Loading progress...")
        with open(output_path, 'r') as f_check:
            for line in f_check:
                try:
                    existing_data = json.loads(line)
                    processed_dids.add(existing_data['target_did'])
                except:
                    continue
        print(f"Skipping {len(processed_dids)} already processed DIDs.")

    # 2. Robust Data Loading
    if not os.path.exists(input_path):
        print(f"Error: Input file {input_path} not found.")
        return

    raw_entries = []
    print(f"Reading input file: {input_path}")

    with open(input_path, 'r') as f:
        content = f.read().strip()

        try:
            loaded_data = json.loads(content)
            raw_entries = loaded_data if isinstance(loaded_data, list) else [loaded_data]
        except json.JSONDecodeError:
            # Fallback for JSONL or non-standard formatting
            for line in content.splitlines():
                line = line.strip().rstrip(',')
                if not line or line in ['[', ']']: continue
                try:
                    raw_entries.append(json.loads(line))
                except json.JSONDecodeError:
                    print(f"Skipping unparseable line: {line[:100]}...")

    # 3. Validation and Filtering
    valid_entries = []
    for entry in raw_entries:
        if not isinstance(entry, dict):
            continue

        did = entry.get('target_did')
        ts = entry.get('timestamp')

        # Skip if already done
        if did in processed_dids:
            continue

        # Check for required keys
        if not did or not ts:
            print(f"⚠️  Skipping entry missing required keys: {json.dumps(entry)[:100]}...")
            continue

        valid_entries.append(entry)

    if not valid_entries:
        print("No new valid entries to process.")
        return

    # 4. Sort by timestamp descending
    print("Sorting entries by timestamp...")
    valid_entries.sort(
        key=lambda x: datetime.fromisoformat(x['timestamp'].replace('Z', '+00:00')),
        reverse=True
    )

    # 5. Initialize Client
    client = Client()
    try:
        print(f"Logging in as {HANDLE}...")
        client.login(HANDLE, password)
    except Exception as e:
        print(f"Login failed: {e}")
        return

    # 6. Process and Write
    print(f"Processing {len(valid_entries)} entries...")

    with open(output_path, 'a') as f_out:
        for data in valid_entries:
            target_did = data['target_did']

            print(f"[{data['timestamp']}] Fetching: {target_did}")

            try:
                profile = client.get_profile(target_did)
                description = profile.description or ""

                # Fetch Latest 3 Posts
                feed = client.get_author_feed(actor=target_did, limit=10)
                post_texts = []
                for item in feed.feed:
                    if item.post.author.did == target_did:
                        post_texts.append(item.post.record.text)
                    if len(post_texts) == 3:
                        break

                result_entry = {
                    "target_did": target_did,
                    "original_timestamp": data['timestamp'],
                    "description": description,
                    "posts": post_texts
                }

                f_out.write(json.dumps(result_entry) + '\n')
                f_out.flush()

            except Exception as e:
                print(f"  ❌ FAILED for {target_did}: {e}")

    print(f"\nDone! Results saved to {output_path}")


if __name__ == "__main__":
    main()