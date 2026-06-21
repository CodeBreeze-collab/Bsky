import os
import json
import random
import time
from youtube_transcript_api import YouTubeTranscriptApi


class YouTubeProcessor:
    def __init__(self, directory):
        self.directory = os.path.abspath(directory)

    def get_video_ids(self, file_path):
        """Reads video IDs from a specific text file, ignoring ' - ' prefix."""
        valid_ids = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    # Remove the ' - ' prefix and any surrounding whitespace/newlines
                    clean_id = line.lstrip('- ').strip()
                    if clean_id:
                        valid_ids.append(clean_id)
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
        return valid_ids

    def download_transcripts(self, video_ids):
        api = YouTubeTranscriptApi()

        for vid_id in video_ids:
            # Check if file exists to avoid redundant API calls
            output_path = f'/Users/hdon/Projects/Tarot/looney_moon/tarot_hateful_spiteful_content/output_json/{vid_id}_transcript.json'
            if os.path.exists(output_path):
                print(f"Skipping {vid_id} (already exists)")
                continue

            print(f"Processing: {vid_id}")
            try:
                raw_result = api.fetch(vid_id)

                # Conversion Logic
                serializable_data = []
                for snippet in raw_result:
                    if hasattr(snippet, 'to_dict'):
                        serializable_data.append(snippet.to_dict())
                    elif hasattr(snippet, '__dict__'):
                        serializable_data.append({k: v for k, v in snippet.__dict__.items() if not k.startswith('_')})
                    else:
                        serializable_data.append(str(snippet))

                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(serializable_data, f, indent=4)

                print(f"  [SUCCESS] Saved {vid_id}_transcript.json")

                # --- RANDOM DELAY ---
                delay = random.uniform(15, 20)
                print(f"  [WAIT] Sleeping for {delay:.2f} seconds...")
                time.sleep(delay)

            except Exception as e:
                print(f"  [ERROR] {vid_id}: {e}")
                time.sleep(10)


if __name__ == "__main__":
    processor = YouTubeProcessor("/Users/hdon/Projects/Tarot/looney_moon/tarot_hateful_spiteful_content")

    # Point this to the text file containing your list of IDs
    list_file_path = "/Users/hdon/Desktop/Looney-TimeStamps/Looney-Video_IDs_to-download-transcript.txt"

    ids = processor.get_video_ids(list_file_path)

    if ids:
        print(f"Found {len(ids)} video IDs. Starting downloads...")
        processor.download_transcripts(ids)
    else:
        print("No valid video IDs found in the file.")