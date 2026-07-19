import datetime
import json
import os
import re
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

    # Clean the base URL by stripping any existing trailing tabs (/videos, /shorts, etc.)
    base_channel_url = re.sub(r'/(videos|shorts|streams)/?$', '', channel_url.rstrip('/'))

    # Explicitly target both content tabs
    target_tabs = [f"{base_channel_url}/videos", f"{base_channel_url}/shorts"]

    print(f"Scanning channel base: {base_channel_url}")
    print(f"Looking for content uploaded since: {cutoff_date.strftime('%Y-%m-%d')} (Last {max_days} days)")

    # 1. Fast initial layout grab (inherits Firefox session)
    ydl_opts_flat = {
        'extract_flat': True,
        'quiet': True,
        'no_warnings': True,
        'cookiesfrombrowser': ('firefox',),
    }

    # 2. Detailed metadata grab for individual date checks (inherits Firefox session)
    ydl_opts_video = {
        'quiet': True,
        'no_warnings': True,
        'cookiesfrombrowser': ('firefox',),
        'format': 'all',  # Forces yt-dlp to ignore missing stream formats and just return metadata
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
                        # Extract full info for the individual item to bypass the flat 'None' date bug
                        video_info = ydl_video.extract_info(video_url, download=False)
                        upload_date = video_info.get('upload_date')

                        if upload_date:
                            if upload_date < cutoff_str:
                                # Break out immediately because the tab lists videos newest -> oldest
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


def download_youtube_transcript(video_url: str, output_dir: str) -> str:
    """Downloads automated English subtitles in json3 format using browser authentication."""
    video_id = extract_video_id(video_url)
    os.makedirs(output_dir, exist_ok=True)

    outtmpl_base = os.path.join(output_dir, video_id)

    # 3. Transcript download settings (inherits Firefox session)
    ydl_opts = {
        'skip_download': True,
        'writeautomaticsub': True,
        'subtitleslangs': ['en*'],
        'subtitlesformat': 'json3',
        'outtmpl': {'default': outtmpl_base},
        'quiet': True,
        'no_warnings': True,
        'cookiesfrombrowser': ('firefox',),
        'format': 'all',  # Prevents any format errors here as well
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([video_url])

    for filename in os.listdir(output_dir):
        if filename.startswith(video_id) and filename.endswith(('.json', '.json3')) and not filename.endswith(
                '_chunked.json'):
            return os.path.join(output_dir, filename)

    raise FileNotFoundError(f"Expected transcript file starting with '{video_id}' was not found.")


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


def run_video_pipeline(video_url: str, output_dir: str, group_window_ms: int = 30000):
    """Executes the transcript download and parsing pipeline for an isolated video."""
    try:
        video_id = extract_video_id(video_url)

        # --- RESTART PROOF CHECK ---
        expected_chunked_file = f"{video_id}_chunked.json"
        final_chunked_path = os.path.join(output_dir, expected_chunked_file)

        if os.path.exists(final_chunked_path):
            print(f"Skipping video ID: {video_id} (Already processed).")
            return

        print(f"Processing video ID: {video_id}...")

        raw_path = download_youtube_transcript(video_url, output_dir)

        # FIX: Explicitly passing final_chunked_path positionally to match the function parameters
        preprocess_and_save_json(raw_path, final_chunked_path, group_window_ms=group_window_ms)
        print(f"[+] Successfully chunked transcript -> {os.path.basename(final_chunked_path)}")
    except Exception as e:
        print(f"[-] Failed processing {video_url}: {e}")


# ==========================================
# EXECUTION ROUTER
# ==========================================
if __name__ == "__main__":
    TARGET_DIR = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/v2/yt_download/channels_chunked/HistoryWithKayleigh"
    WINDOW_MS = 10000

    PROCESS_WHOLE_CHANNEL = True

    if PROCESS_WHOLE_CHANNEL:
        channel_target = "https://www.youtube.com/@HistoryWithKayleigh"
        days_limit = 1460

        urls_to_process = get_videos_from_channel(channel_target, max_days=days_limit)
        print("=" * 50)
        for index, url in enumerate(urls_to_process, start=1):
            print(f"\n[Video {index}/{len(urls_to_process)}]")
            run_video_pipeline(url, TARGET_DIR, WINDOW_MS)

    else:
        single_video_url = "https://www.youtube.com/shorts/XI2xiUe5AJM"
        print("Running in single video pipeline mode...")
        run_video_pipeline(single_video_url, TARGET_DIR, WINDOW_MS)

    print("\nPipeline process execution finished.")