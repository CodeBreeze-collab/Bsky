import os
import re
import yt_dlp
import argparse

PATTERN = re.compile(r"analysis_(.+?)_transcript\.json$")

def extract_video_ids(folder_path):
    video_ids = set()

    for filename in os.listdir(folder_path):
        match = PATTERN.match(filename)
        if match:
            video_ids.add(match.group(1))

    return sorted(video_ids)


def download_videos(video_ids, output_folder):
    urls = [f"https://www.youtube.com/watch?v={vid}" for vid in video_ids]

    ydl_opts = {
        "outtmpl": os.path.join(output_folder, "%(title)s.%(ext)s"),
        "format": "bestvideo+bestaudio/best",
        "noplaylist": True,
        "retries": 3,
        "quiet": False,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download(urls)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", help="Folder containing analysis_*_transcript.json files")
    parser.add_argument("--out", default="downloads", help="Output folder for videos")

    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)

    video_ids = extract_video_ids(args.folder)

    print(f"Found {len(video_ids)} video IDs:")
    for vid in video_ids:
        print(" -", vid)

    download_videos(video_ids, args.out)


if __name__ == "__main__":
    main()