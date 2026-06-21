import os
import json
import logging
import argparse
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter, JSONFormatter  # added JSONFormatter

# --- LOGGING CONFIG ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


def fetch_and_save_transcript(video_id: str, output_dir: str):
    logging.info(f"📁 Ensuring target output directory exists: {output_dir}")
    os.makedirs(output_dir, exist_ok=True)

    txt_path = os.path.join(output_dir, f"analysis_{video_id}_transcript.txt")
    json_path = os.path.join(output_dir, f"analysis_{video_id}_transcript.json")

    logging.info(f"📡 Initializing connection to YouTube API for Video ID: {video_id}...")

    try:
        # 1. Instantiate the API client and fetch the data wrapper
        api_client = YouTubeTranscriptApi()
        raw_transcript = api_client.fetch(video_id)

        logging.info("⚡ Connection successful! Processing layout formatters...")

        # 2. Save Timed Structural JSON using the built-in JSONFormatter
        logging.info(f"📝 Serializing structural data to JSON: {json_path}")
        json_formatter = JSONFormatter()
        json_string = json_formatter.format_transcript(raw_transcript)

        # Parse and re-dump just to apply your pretty indent/formatting cleanly
        json_payload = json.loads(json_string)
        with open(json_path, 'w', encoding='utf-8') as jf:
            json.dump(json_payload, jf, indent=2, ensure_ascii=False)
        logging.info("✅ JSON compilation complete.")

        # 3. Save Plain Text format
        logging.info(f"📖 Stitching text chunks into clean reading prose: {txt_path}")
        text_formatter = TextFormatter()
        clean_text = text_formatter.format_transcript(raw_transcript)

        # Collapse ugly line breaks into smooth paragraph format
        clean_text = clean_text.replace("\n", " ")

        with open(txt_path, 'w', encoding='utf-8') as tf:
            tf.write(clean_text)
        logging.info("✅ Plain text formatting complete.")

    except Exception as e:
        logging.error(f"❌ Failed processing sequence for video {video_id}.", exc_info=True)

def main():
    parser = argparse.ArgumentParser(description="Programmatically fetch and store YouTube transcripts.")
    parser.add_argument("video_id", help="The 11-character YouTube video ID")
    parser.add_argument("--out", default="transcripts", help="Target directory")

    args = parser.parse_args()
    fetch_and_save_transcript(args.video_id, args.out)


if __name__ == "__main__":
    main()