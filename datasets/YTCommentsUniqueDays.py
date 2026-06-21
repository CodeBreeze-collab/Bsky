import json
import glob
import os


def get_unique_dates(root_dir='.'):
    """
    Recursively finds all .jsonl files, extracts unique dates from
    'published_at', and returns them sorted.
    """
    unique_dates = set()

    # Recursively find all .jsonl files in the current directory and subdirectories
    search_path = os.path.join('/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/v2/datasets/', '**', '*.jsonl')
    files = glob.glob(search_path, recursive=True)

    for file_path in files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                        published_at = data.get('published_at', '')

                        # The format is ISO 8601 (e.g., '2026-03-11T22:02:49Z')
                        # We split by 'T' to get the date part
                        if published_at:
                            date_part = published_at.split('T')[0]
                            unique_dates.add(date_part)

                    except json.JSONDecodeError:
                        print(f"Skipping invalid JSON line in {file_path}")
                        continue
        except Exception as e:
            print(f"Could not read file {file_path}: {e}")

    # Sort the unique dates
    return sorted(list(unique_dates))


if __name__ == "__main__":
    dates = get_unique_dates()

    for date in dates:
        print(date)