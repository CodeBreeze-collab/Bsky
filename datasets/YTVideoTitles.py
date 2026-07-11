import json
import glob
import os
from collections import defaultdict


def get_dates_and_titles(root_dir='/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/v2/datasets/'):
    """
    Groups video titles by their published date from .jsonl files.
    """
    # Using defaultdict to store a set of titles for each date
    date_map = defaultdict(set)

    search_path = os.path.join(root_dir, '**', '*.jsonl')
    files = glob.glob(search_path, recursive=True)

    for file_path in files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                        published_at = data.get('published_at')
                        video_id = data.get('video_id')

                        if published_at and video_id:
                            date_part = published_at.split('T')[0]
                            # Storing video_id (or you could store title if available)
                            date_map[date_part].add(video_id)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            print(f"Could not read file {file_path}: {e}")

    return date_map


if __name__ == "__main__":
    data = get_dates_and_titles()

    # Sort dates chronologically
    for date in sorted(data.keys()):
        print(f"--- {date} ---")
        for video in sorted(data[date]):
            print(video)
        print()  # Adds a blank line for readability