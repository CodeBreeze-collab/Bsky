import yt_dlp


def get_recent_video_ids(channel_url, since_date):
    """
    Fetches video IDs from a channel uploaded after since_date.
    since_date format: 'YYYYMMDD' (e.g., '20240101')
    """
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,  # Only get metadata, don't enter the video
        'force_generic_extractor': False,
        'daterange': yt_dlp.utils.DateRange(start=since_date),
    }

    video_ids = []

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # extract_info on a channel returns a list of entries (videos)
            channel_info = ydl.extract_info(channel_url, download=False)

            if 'entries' in channel_info:
                for entry in channel_info['entries']:
                    if entry:
                        video_ids.append(entry['id'])

        return video_ids
    except Exception as e:
        print(f"❌ Error fetching channel data: {e}")
        return []


# --- CONFIGURATION ---
CHANNEL_URL = 'https://www.youtube.com/@lumenmoontarot/videos'
DATE_LIMIT = '20250501'  # Format: YYYYMMDD (April 1st, 2024)

print(f"--- Fetching videos uploaded since {DATE_LIMIT} ---")
ids = get_recent_video_ids(CHANNEL_URL, DATE_LIMIT)

print(f"✅ Found {len(ids)} videos:")
for vid in ids:
    print(f"{vid}")