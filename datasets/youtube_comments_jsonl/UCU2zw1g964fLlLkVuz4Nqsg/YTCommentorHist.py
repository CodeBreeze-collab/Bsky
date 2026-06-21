import json
import csv
from pathlib import Path
from collections import defaultdict

def count_videos_per_commenter(root_folder, output_file):
    commenter_activity = defaultdict(set)
    path = Path(root_folder)

    for file_path in path.rglob("*.jsonl"):
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data = json.loads(line)
                    channel_id = data.get('channel_id')
                    video_id = data.get('video_id')

                    if channel_id and video_id:
                        commenter_activity[channel_id].add(video_id)
                except json.JSONDecodeError:
                    continue

    sorted_activity = sorted(
        commenter_activity.items(),
        key=lambda item: len(item[1]),
        reverse=True
    )

    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(hook := csvfile)
        writer.writerow(['commenter_id', 'channel_url', 'unique_video_count'])

        for channel_id, videos in sorted_activity:
            # Create the reliable channel URL using the ID
            channel_url = f"https://www.youtube.com/channel/{channel_id}"
            writer.writerow([channel_id, channel_url, len(videos)])

    print(f"Success! Report saved to {output_file}")

# Usage
count_videos_per_commenter('/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/v2/datasets/youtube_comments_jsonl/UCU2zw1g964fLlLkVuz4Nqsg/',
                           'commenter_video_counts_UCU2zw1g964fLlLkVuz4Nqsg_w-handle.csv')