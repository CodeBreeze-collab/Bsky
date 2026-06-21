import json
import re
import os


def extract_tags(text):
    """Extracts hashtags from text, defaults to ['General'] if none found."""
    tags = re.findall(r"#(\w+)", text)
    return tags if tags else ["General"]


def process_and_sort_files(input_paths, output_path, target_phrase):
    """
    Reads files, filters by phrase (no date filtering), and sorts by date ascending.
    """
    all_matches = []

    for file_path in input_paths:
        if not os.path.exists(file_path):
            print(f"File not found: {file_path}")
            continue

        print(f"--- Scanning: {os.path.basename(file_path)} ---")

        with open(file_path, 'r', encoding='utf-8') as infile:
            for line in infile:
                if not line.strip(): continue
                try:
                    data = json.loads(line)
                    text = data.get("text", "")
                    raw_date = data.get("date", "")

                    # 1. Filter Phrase only
                    if target_phrase.lower() not in text.lower():
                        continue

                    # 2. Create entry (including date)
                    new_entry = {
                        "channel": "v_search",
                        "text": text,
                        "date": raw_date,
                        "links": data.get("urls", []),
                        "tags": extract_tags(text)
                    }

                    # Store as a tuple: (sort_key, entry)
                    all_matches.append((raw_date, new_entry))

                except Exception as e:
                    print(f"  Error parsing line: {e}")
                    continue

    # Sort matches by the date string (ascending)
    all_matches.sort(key=lambda x: x[0])

    # Write sorted entries to output file
    with open(output_path, 'w', encoding='utf-8') as outfile:
        for _, entry in all_matches:
            outfile.write(json.dumps(entry) + '\n')

    return len(all_matches)


if __name__ == "__main__":
    # --- CONFIGURATION ---
    base_dir = '/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/my_posts/'
    filenames = [
        'newenglandtopnews_bsky_social_posts.jsonl',
        'westcoastnews_bsky_social_posts.jsonl',
        'floridanews_bsky_social_posts.jsonl'
    ]
    input_files = [os.path.join(base_dir, f) for f in filenames]
    output_file = os.path.join(base_dir, 'stalking-2025-05-22.jsonl')

    # Run Process (No date parameters needed)
    count = process_and_sort_files(input_files, output_file, "stalk")
    print(f"\nSuccess! {count} sorted lines saved to {output_file}.")