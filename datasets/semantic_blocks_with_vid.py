import datetime
import json
import os
import re
import subprocess  # Added for calling FFmpeg
import shutil
import yt_dlp


def ms_to_timestamp(ms: int) -> str:
    """Converts milliseconds to an HH:MM:SS or MM:SS string format."""
    seconds = ms / 1000
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    if hours > 0:
        return f"{hours:02}:{minutes:02}:{secs:02}"
    return f"{minutes:02}:{secs:02}"


def extract_video_id(url: str) -> str:
    """Extracts the 11-character YouTube video ID from various URL patterns."""
    match = re.search(r'(?:v=|\/v\/|youtu\.be\/|\/embed\/|\/shorts\/)([a-zA-Z0-9_-]{11})', url)
    if match:
        return match.group(1)
    raise ValueError(f"Could not extract a valid YouTube video ID from URL: {url}")


def get_videos_from_channel(channel_url: str, max_days: int) -> list:
    """
    Scans BOTH the /videos and /shorts tabs of a YouTube channel and returns
    a deduplicated list of video URLs uploaded within the specified number of days.
    """
    cutoff_date = datetime.date.today() - datetime.timedelta(days=max_days)
    cutoff_str = cutoff_date.strftime('%Y%m%d')

    base_channel_url = re.sub(r'/(videos|shorts|streams)/?$', '', channel_url.rstrip('/'))
    target_tabs = [f"{base_channel_url}/videos", f"{base_channel_url}/shorts"]

    print(f"Scanning channel base: {base_channel_url}")
    print(f"Looking for content uploaded since: {cutoff_date.strftime('%Y-%m-%d')} (Last {max_days} days)")

    ydl_opts_flat = {
        'extract_flat': True,
        'quiet': True,
        'no_warnings': True,
        'cookiesfrombrowser': ('firefox',),
    }

    ydl_opts_video = {
        'quiet': True,
        'no_warnings': True,
        'cookiesfrombrowser': ('firefox',),
        'format': 'all',
    }

    unique_video_urls = set()

    with yt_dlp.YoutubeDL(ydl_opts_flat) as ydl_flat, yt_dlp.YoutubeDL(ydl_opts_video) as ydl_video:
        for tab_url in target_tabs:
            tab_name = tab_url.split('/')[-1].upper()
            print(f"-> Checking tab: {tab_name}")
            try:
                channel_info = ydl_flat.extract_info(tab_url, download=False)

                if 'entries' not in channel_info or not channel_info['entries']:
                    continue

                for entry in channel_info['entries']:
                    if not entry:
                        continue

                    video_id = entry.get('id')
                    if not video_id or len(video_id) != 11:
                        continue

                    video_url = f"https://www.youtube.com/watch?v={video_id}"

                    try:
                        video_info = ydl_video.extract_info(video_url, download=False)
                        upload_date = video_info.get('upload_date')

                        if upload_date:
                            if upload_date < cutoff_str:
                                print(f"   [-] Hit older video ({upload_date}). Breaking out of {tab_name} scan.")
                                break

                            print(f"   [+] Matches criteria ({upload_date}): {video_url}")
                            unique_video_urls.add(video_url)

                    except Exception as ev:
                        print(f"   [-] Error verifying date for video {video_id}: {ev}")

            except Exception as e:
                print(f"   [-] Error parsing tab metadata for {tab_url}: {e}")

    video_list = list(unique_video_urls)
    print(f"[+] Found {len(video_list)} total unique videos/shorts matching criteria.")
    return video_list


def download_media_and_transcript(video_url: str, output_dir: str) -> tuple:
    """
    Downloads BOTH the automated English subtitles and a low-resolution MP4 video file.
    Returns a tuple of (transcript_file_path, video_file_path).
    """
    video_id = extract_video_id(video_url)
    os.makedirs(output_dir, exist_ok=True)

    # Use a clear template pattern so we know exactly what names to look for
    outtmpl_base = os.path.join(output_dir, f"{video_id}.%(ext)s")

    ydl_opts = {
        'skip_download': False,
        'writeautomaticsub': True,
        'subtitleslangs': ['en*'],
        'subtitlesformat': 'json3',
        'outtmpl': outtmpl_base,
        'quiet': True,
        'no_warnings': True,
        'cookiesfrombrowser': ('firefox',),
        # FIX: Downloads video (up to 720p) AND audio, then merges them cleanly
        'format': 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best',
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([video_url])

    transcript_path = None
    video_path = None

    # Scan the directory to capture the final precise names settled on by yt-dlp
    for filename in os.listdir(output_dir):
        if filename.startswith(video_id):
            full_path = os.path.join(output_dir, filename)
            if filename.endswith(('.json', '.json3')) and not filename.endswith('_chunked.json'):
                transcript_path = full_path
            elif filename.endswith('.mp4'):
                video_path = full_path

    if not transcript_path:
        raise FileNotFoundError(f"Expected transcript file for '{video_id}' was not found.")
    if not video_path:
        raise FileNotFoundError(f"Expected video file for '{video_id}' was not found.")

    return transcript_path, video_path


def extract_video_frames(video_path: str, frames_output_dir: str, interval_seconds: int):
    """Uses raw FFmpeg binary to extract one high-quality JPEG frame every N seconds."""
    os.makedirs(frames_output_dir, exist_ok=True)

    # Check if directory already has extractions to preserve restart-proofing integrity
    if len(os.listdir(frames_output_dir)) > 0:
        print(f"   [~] Frames directory not empty. Skipping FFmpeg generation pass.")
        return

    print(f"   [>] Launching FFmpeg frame extraction (1 frame every {interval_seconds}s)...")

    # Output file format pattern forces zero-padded chronological numbering (frame_0001.jpg)
    output_pattern = os.path.join(frames_output_dir, "frame_%04d.jpg")

    # FFmpeg invocation arguments
    # -vf "fps=1/N" drops all but one frame for every N sequence blocks
    # -q:v 3 balances crystal clear visual boundaries with optimized drive compression
    cmd = [
        'ffmpeg', '-y',
        '-i', video_path,
        '-vf', f"fps=1/{interval_seconds}",
        '-q:v', '3',
        output_pattern
    ]

    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
        print(
            f"   [+] FFmpeg frame processing sequence complete -> {len(os.listdir(frames_output_dir))} frames generated.")
    except subprocess.CalledProcessError as e:
        print(f"   [-] FFmpeg compilation failure error logs: {e.stderr.decode().strip()}")
        raise e


def preprocess_and_save_json(input_file_path: str, output_file_path: str, group_window_ms=30000):
    """Aggregates raw choppy lines into dense semantic chunk windows."""
    with open(input_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    events = data.get('events', data) if isinstance(data, dict) else data
    processed_chunks = []
    current_chunk_text, current_start_ms, current_end_ms = [], None, None

    for event in events:
        if 'tStartMs' not in event:
            continue
        start_ms = event['tStartMs']
        end_ms = start_ms + event.get('dDurationMs', 0)

        text = ""
        if 'text' in event:
            text = event['text']
        elif 'segs' in event:
            text = "".join([seg.get('utf8', '') for seg in event['segs'] if 'utf8' in seg])

        text = text.strip()
        if not text:
            continue

        if current_start_ms is None:
            current_start_ms, current_end_ms = start_ms, end_ms
            current_chunk_text.append(text)
        elif (start_ms - current_start_ms) < group_window_ms:
            current_chunk_text.append(text)
            current_end_ms = max(current_end_ms, end_ms)
        else:
            processed_chunks.append({
                "start_time": ms_to_timestamp(current_start_ms),
                "end_time": ms_to_timestamp(current_end_ms),
                "text": " ".join(current_chunk_text).replace("\n", " ").strip()
            })
            current_start_ms, current_end_ms, current_chunk_text = start_ms, end_ms, [text]

    if current_start_ms is not None:
        processed_chunks.append({
            "start_time": ms_to_timestamp(current_start_ms),
            "end_time": ms_to_timestamp(current_end_ms),
            "text": " ".join(current_chunk_text).replace("\n", " ").strip()
        })

    with open(output_file_path, 'w', encoding='utf-8') as f:
        json.dump(processed_chunks, f, indent=4, ensure_ascii=False)


def run_video_pipeline(video_url: str, output_dir: str, group_window_ms: int = 30000, keep_video: bool = False):
    """Executes the full media download, transcript processing, and image frame extraction pipeline."""
    try:
        video_id = extract_video_id(video_url)

        # --- RESTART PROOF CHECK ---
        expected_chunked_file = f"{video_id}_chunked.json"
        final_chunked_path = os.path.join(output_dir, expected_chunked_file)
        frames_dir = os.path.join(output_dir, f"{video_id}_frames")

        # If both the text chunks and extracted frames exist, bypass entirely
        if os.path.exists(final_chunked_path) and os.path.exists(frames_dir) and len(os.listdir(frames_dir)) > 0:
            print(f"Skipping video ID: {video_id} (Transcript and frames already processed).")
            return

        print(f"\nProcessing video ID: {video_id}...")

        # 1. Unified Download Step (Both subtitle track and low-res media binary)
        raw_json_path, video_mp4_path = download_media_and_transcript(video_url, output_dir)

        # 2. Extract Frames using FFmpeg
        interval_secs = group_window_ms // 1000
        extract_video_frames(video_mp4_path, frames_dir, interval_secs)

        # 3. Clean up the raw text transcript into semantic chunk files
        preprocess_and_save_json(raw_json_path, final_chunked_path, group_window_ms=group_window_ms)
        print(f"[+] Successfully chunked transcript -> {os.path.basename(final_chunked_path)}")

        # 4. Optional Storage Cleanup
        if not keep_video:
            print(f"   [-] Purging heavy raw video binary file to optimize local workspace storage...")
            if os.path.exists(video_mp4_path):
                os.remove(video_mp4_path)

    except Exception as e:
        print(f"[-] Failed processing execution track for {video_url}: {e}")


# ==========================================
# EXECUTION ROUTER
# ==========================================
if __name__ == "__main__":
    TARGET_DIR = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/v2/yt_download/channels_chunked_vid/JustineCooksVegan"
    WINDOW_MS = 10000  # 10 second windows = 1 image extracted per 10 seconds of runtime

    PROCESS_WHOLE_CHANNEL = True
    KEEP_VIDEO_FILE = False  # Set to True if you want to keep the downloaded mp4 files locally

    if PROCESS_WHOLE_CHANNEL:
        channel_target = "https://www.youtube.com/@JustineCooksVegan"
        days_limit = 1460

        urls_to_process = get_videos_from_channel(channel_target, max_days=days_limit)
        print("=" * 50)
        for index, url in enumerate(urls_to_process, start=1):
            print(f"\n[Video {index}/{len(urls_to_process)}]")
            run_video_pipeline(url, TARGET_DIR, WINDOW_MS, keep_video=KEEP_VIDEO_FILE)

    else:
        single_video_url = "https://www.youtube.com/shorts/XI2xiUe5AJM"
        print("Running in single video pipeline mode...")
        run_video_pipeline(single_video_url, TARGET_DIR, WINDOW_MS, keep_video=KEEP_VIDEO_FILE)

    print("\nPipeline process execution finished.")