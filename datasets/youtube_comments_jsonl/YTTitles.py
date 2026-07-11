import datetime
from datetime import timezone
from googleapiclient.discovery import build
import json
import os


class YouTubeVideoExporter:
    def __init__(self, api_key: str, channel_id: str, days_after: int, days_before: int, output_file: str):
        self.api_key = api_key
        self.channel_id = channel_id
        self.days_after = days_after
        self.days_before = days_before
        self.output_file = output_file
        self.youtube = build("youtube", "v3", developerKey=self.api_key)

    def get_time_window(self):
        now = datetime.datetime.now(timezone.utc)
        start_date = now - datetime.timedelta(days=self.days_after)
        end_date = now - datetime.timedelta(days=self.days_before)
        return start_date, end_date

    def get_uploads_playlist(self):
        res = self.youtube.channels().list(
            part="contentDetails",
            id=self.channel_id
        ).execute()
        return res["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

    def get_videos_in_range(self, playlist_id, start_date, end_date):
        videos = []
        next_page = None

        while True:
            res = self.youtube.playlistItems().list(
                part="snippet",
                playlistId=playlist_id,
                maxResults=50,
                pageToken=next_page
            ).execute()

            for item in res["items"]:
                snip = item["snippet"]
                published_at = datetime.datetime.fromisoformat(
                    snip["publishedAt"].replace("Z", "+00:00")
                )

                if start_date <= published_at <= end_date:
                    videos.append({
                        "video_id": snip["resourceId"]["videoId"],
                        "publication_date": snip["publishedAt"],
                        "title": snip["title"]
                    })

            next_page = res.get("nextPageToken")
            if not next_page:
                break
        return videos

    def write_to_jsonl(self, videos):
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(self.output_file), exist_ok=True)

        with open(self.output_file, "w", encoding="utf-8") as f:
            for v in videos:
                f.write(json.dumps(v, ensure_ascii=False) + "\n")

    def run(self):
        start_date, end_date = self.get_time_window()
        playlist = self.get_uploads_playlist()
        videos = self.get_videos_in_range(playlist, start_date, end_date)

        print(f"Found {len(videos)} videos. Writing to {self.output_file}...")
        self.write_to_jsonl(videos)
        print("Done.")


if __name__ == "__main__":
    exporter = YouTubeVideoExporter(
        api_key="AIzaSyB6m8GdgJpdra56s8wjs-coi_9NKU6DNrE",
        channel_id="UCU2zw1g964fLlLkVuz4Nqsg",
        days_after=1100,
        days_before=731,
        output_file="/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/v2/datasets/youtube_comments_jsonl/UCU2zw1g964fLlLkVuz4Nqsg/video_titles_UCU2zw1g964fLlLkVuz4Nqsg_731-1100.jsonl"
    )
    exporter.run()