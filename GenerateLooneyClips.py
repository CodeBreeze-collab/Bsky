import os
import json
import subprocess

# --- CONFIGURATION ---
ANALYSIS_DIR = '/Users/hdon/Projects/Tarot/looney_moon/tarot_hateful_spiteful_content/analysis/'
VIDEO_DIR = '/Users/hdon/Projects/Tarot/looney_moon/looney_videos/'
OUTPUT_DIR = '/Users/hdon/Projects/Tarot/looney_moon/tarot_hateful_spiteful_content/supercuts/'

os.makedirs(OUTPUT_DIR, exist_ok=True)


def create_supercut(json_path, video_path, output_path):
    with open(json_path, 'r') as f:
        segments = json.load(f)

    if not segments:
        print(f"No segments found for {json_path}")
        return

    # Temporary file to store the list of cut segments for ffmpeg concat
    list_file_path = "concat_list.txt"
    temp_clips = []

    try:
        for i, seg in enumerate(segments):
            start = seg['start']
            duration = round(seg['end'] - seg['start'], 2)
            temp_clip = f"temp_part_{i}.mp4"

            # Extract segment without re-encoding (very fast)
            cmd = [
                'ffmpeg', '-y', '-ss', str(start), '-i', video_path,
                '-t', str(duration), '-c', 'copy', temp_clip
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            temp_clips.append(temp_clip)

        # Create the concat list file
        with open(list_file_path, 'w') as f:
            for clip in temp_clips:
                f.write(f"file '{clip}'\n")

        # Concatenate all parts into the final supercut
        concat_cmd = [
            'ffmpeg', '-y', '-f', 'concat', '-safe', '0',
            '-i', list_file_path, '-c', 'copy', output_path
        ]
        subprocess.run(concat_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        print(f"✅ Created supercut: {output_path}")

    finally:
        # Cleanup temp files
        if os.path.exists(list_file_path):
            os.remove(list_file_path)
        for clip in temp_clips:
            if os.path.exists(clip):
                os.remove(clip)


def main():
    analysis_files = [f for f in os.listdir(ANALYSIS_DIR) if f.startswith('analysis_') and f.endswith('.json')]

    for filename in analysis_files:
        # Convert 'analysis_video1_transcript.json' -> 'video1.mp4'
        # Adjust this logic based on your exact file naming convention
        base_name = filename.replace('analysis_', '').replace('_transcript.json', '')
        video_filename = f"{base_name}.mp4"
        video_path = os.path.join(VIDEO_DIR, video_filename)

        json_path = os.path.join(ANALYSIS_DIR, filename)
        output_path = os.path.join(OUTPUT_DIR, f"supercut_{base_name}.mp4")

        if os.path.exists(video_path):
            print(f"--- Processing {video_filename} ---")
            create_supercut(json_path, video_path, output_path)
        else:
            print(f"⚠️ Video not found for {filename} (Expected: {video_filename})")


if __name__ == "__main__":
    main()