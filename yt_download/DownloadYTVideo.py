import os
import argparse
import yt_dlp

def download_video(video_id, output_folder):
    # Construct the standard YouTube URL from the video ID
    url = f"https://www.youtube.com/watch?v={video_id}"

    ydl_opts = {
        # Using %(id)s names the file exactly as the YouTube ID
        "outtmpl": os.path.join(output_folder, "%(id)s.%(ext)s"),
        "format": "bestvideo+bestaudio/best",
        # Force the merged video/audio stream into an mp4 container
        "merge_output_format": "mp4",
        "noplaylist": True,
        "retries": 3,
        "quiet": False,
    }

    print(f"Starting download for video ID: {video_id}")
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])


def main():
    parser = argparse.ArgumentParser(description="Download a YouTube video by its ID.")
    parser.add_argument("video_id", help="The 11-character YouTube video ID (e.g., dQw4w9WgXcQ)")
    parser.add_argument("--out", default="downloads", help="Output folder for the downloaded video")

    args = parser.parse_args()

    # Ensure the output directory exists
    os.makedirs(args.out, exist_ok=True)

    download_video(args.video_id, args.out)


if __name__ == "__main__":
    main()