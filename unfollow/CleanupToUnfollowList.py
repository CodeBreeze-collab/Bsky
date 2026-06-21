import json
import os


def offline_cleanup(following_file, results_file, output_file="cleaned_results.jsonl"):
    # 1. Load the DIDs of people you are actually following
    print(f"📖 Reading source of truth: {following_file}")
    active_dids = set()

    if not os.path.exists(following_file):
        print(f"❌ Error: {following_file} not found.")
        return

    with open(following_file, 'r') as f:
        for line in f:
            try:
                data = json.loads(line)
                active_dids.add(data['did'])
            except (json.JSONDecodeError, KeyError):
                continue

    print(f"✅ Found {len(active_dids)} unique active follows.")

    # 2. Filter the results file
    print(f"🧹 Filtering {results_file}...")
    cleaned_entries = []
    removed_count = 0

    if not os.path.exists(results_file):
        print(f"❌ Error: {results_file} not found.")
        return

    with open(results_file, 'r') as f:
        for line in f:
            try:
                entry = json.loads(line)
                # Only keep if the DID is in our active following list
                if entry.get('did') in active_dids:
                    cleaned_entries.append(entry)
                else:
                    removed_count += 1
            except (json.JSONDecodeError, KeyError):
                continue

    # 3. Write the cleaned data
    with open(output_file, 'w') as f:
        for entry in cleaned_entries:
            f.write(json.dumps(entry) + '\n')

    print(f"---")
    print(f"✨ Success!")
    print(f"📥 Total processed: {len(cleaned_entries) + removed_count}")
    print(f"🗑️ Ghosts removed: {removed_count}")
    print(f"💾 Cleaned file saved as: {output_file}")


if __name__ == "__main__":
    # Update these filenames to match yours
    FOLLOWING_LIST = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/v2/unfollow/follows_cache_newenglandtopnews.bsky.social.jsonl"
    AUDIT_RESULTS = "results.jsonl"

    offline_cleanup(FOLLOWING_LIST, AUDIT_RESULTS)