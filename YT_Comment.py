import datetime
from datetime import timezone
import json
import os
from googleapiclient.discovery import build


class YouTubeCommentExporter:
    def __init__(
        self,
        api_key: str,
        channel_id: str,
        days_after: int,
        days_before: int,
        output_dir: str = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/v2/datasets/youtube_comments_jsonl/UCU2zw1g964fLlLkVuz4Nqsg/jun1-91-180-days/",
    ):
        self.api_key = api_key
        self.channel_id = channel_id
        self.days_after = days_after
        self.days_before = days_before
        self.output_dir = output_dir

        self.youtube = build("youtube", "v3", developerKey=self.api_key)

    # -------------------------
    # Date window
    # -------------------------
    def get_time_window(self):
        now = datetime.datetime.now(timezone.utc)

        start_date = now - datetime.timedelta(days=self.days_after)
        end_date = now - datetime.timedelta(days=self.days_before)

        return start_date, end_date

    # -------------------------
    # Channel → uploads playlist
    # -------------------------
    def get_uploads_playlist(self):
        res = self.youtube.channels().list(
            part="contentDetails",
            id=self.channel_id
        ).execute()

        return res["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

    # -------------------------
    # Fetch videos in range
    # -------------------------
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
                        "title": snip["title"],
                        "published_at": snip["publishedAt"]
                    })

            next_page = res.get("nextPageToken")
            if not next_page:
                break

        return videos

    # -------------------------
    # Fetch comments
    # -------------------------
    def fetch_comments(self, video_id):
        comments = []
        next_page = None

        while True:
            try:
                res = self.youtube.commentThreads().list(
                    part="snippet",
                    videoId=video_id,
                    maxResults=100,
                    pageToken=next_page,
                    textFormat="plainText"
                ).execute()
            except Exception:
                break  # comments disabled or quota issue

            for item in res.get("items", []):
                top = item["snippet"]["topLevelComment"]["snippet"]

                comments.append({
                    "channel_name": top.get("authorDisplayName"),
                    "channel_url": top.get("authorChannelUrl"),
                    "channel_id": top.get("authorChannelId", {}).get("value"),
                    "comment": top.get("textDisplay"),
                    "published_at": top.get("publishedAt"),
                    "video_id": video_id
                })

            next_page = res.get("nextPageToken")
            if not next_page:
                break

        return comments

    # -------------------------
    # Write JSONL per video
    # -------------------------
    def write_jsonl(self, video_id, comments):
        os.makedirs(self.output_dir, exist_ok=True)
        path = os.path.join(self.output_dir, f"{video_id}.jsonl")

        with open(path, "w", encoding="utf-8") as f:
            for c in comments:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")

    # -------------------------
    # Main runner
    # -------------------------
    def run(self):
        start_date, end_date = self.get_time_window()

        playlist = self.get_uploads_playlist()
        videos = self.get_videos_in_range(playlist, start_date, end_date)

        print(f"Found {len(videos)} videos in range:")
        print(f"  Start: {start_date}")
        print(f"  End:   {end_date}")

        for i, v in enumerate(videos):
            print(f"[{i+1}/{len(videos)}] {v['title']}")

            comments = self.fetch_comments(v["video_id"])
            self.write_jsonl(v["video_id"], comments)

            print(f"  → wrote {len(comments)} comments")


# -------------------------
# Entry point
# -------------------------
if __name__ == "__main__":
    exporter = YouTubeCommentExporter(
        api_key="AIzaSyB6m8GdgJpdra56s8wjs-coi_9NKU6DNrE",
        channel_id="UCU2zw1g964fLlLkVuz4Nqsg",
        days_after=365,   # older bound
        days_before=181    # newer bound
    )

    exporter.run()