import asyncio
import csv
from TikTokApi import TikTokApi

VIDEO_URL = "https://www.tiktok.com/@maixiongmi/video/7601689820573863223"

async def main():
    async with TikTokApi() as api:
        await api.create_sessions(
            browser="chromium",
            headless=False,
        )

        video = api.video(url=VIDEO_URL)

        comments_data = []

        async for comment in video.comments(count=200):
            username = comment.author.username
            text = comment.text

            comments_data.append([username, text])

            # Fetch replies
            async for reply in comment.replies():
                reply_username = reply.author.username
                reply_text = reply.text
                comments_data.append([reply_username, reply_text])

        # Save to CSV
        with open("tiktok_comments.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Username", "Comment"])
            writer.writerows(comments_data)

    print("Saved to tiktok_comments.csv")

asyncio.run(main())
