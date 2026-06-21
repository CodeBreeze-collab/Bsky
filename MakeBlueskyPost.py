import os
import re
import requests
import cloudscraper
from bs4 import BeautifulSoup
import json
import time
from datetime import datetime, timezone


class BlueskyClient:
    BASE_URL = "https://bsky.social/xrpc"
    # BLUESKY_HANDLE_ne_news
    # BLUESKY_APP_PASSWORD_ne_news

    # BLUESKY_HANDLE_dt_news
    # BLUESKY_APP_PASSWORD_dt_news

    def __init__(self):
        self.handle = os.getenv("BLUESKY_HANDLE", "")
        self.app_password = os.getenv("BLUESKY_HANDLE", "")

        if not self.handle or not self.app_password:
            raise RuntimeError("BLUESKY_HANDLE and BLUESKY_APP_PASSWORD must be set")

        # Initialize cloudscraper to reuse across the session
        self.scraper = cloudscraper.create_scraper(
            browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
        )

        self.access_jwt = None
        self.did = None
        self._login()

    def _login(self):
        url = f"{self.BASE_URL}/com.atproto.server.createSession"
        response = requests.post(url, json={"identifier": self.handle, "password": self.app_password})
        response.raise_for_status()
        data = response.json()
        self.access_jwt, self.did = data["accessJwt"], data["did"]

    def _find_url_facets(self, text: str):
        """Calculates facets using UTF-8 byte offsets."""
        facets = []
        url_pattern = r"(https?://\S+)"
        for match in re.finditer(url_pattern, text):
            url = match.group(0)
            start_byte = len(text[:match.start()].encode("utf-8"))
            end_byte = start_byte + len(url.encode("utf-8"))
            facets.append({
                "index": {"byteStart": start_byte, "byteEnd": end_byte},
                "features": [{"$type": "app.bsky.richtext.facet#link", "uri": url}]
            })
        return facets

    def _upload_blob(self, image_url: str):
        """Downloads image via cloudscraper and uploads to Bluesky."""
        try:
            img_res = self.scraper.get(image_url, timeout=10)
            img_res.raise_for_status()

            if len(img_res.content) > 1000000:  # 1MB Limit
                return None

            url = f"{self.BASE_URL}/com.atproto.repo.uploadBlob"
            headers = {
                "Authorization": f"Bearer {self.access_jwt}",
                "Content-Type": img_res.headers.get("Content-Type", "image/jpeg")
            }
            response = requests.post(url, headers=headers, data=img_res.content)
            response.raise_for_status()
            return response.json()["blob"]
        except Exception as e:
            print(f"  > Thumbnail upload skipped: {e}")
            return None

    def _get_external_embed(self, url: str):
        """Scrapes metadata using cloudscraper to bypass Cloudflare."""
        try:
            res = self.scraper.get(url, timeout=15)
            res.raise_for_status()

            soup = BeautifulSoup(res.text, 'html.parser')

            og_title = soup.find("meta", property="og:title")
            og_desc = soup.find("meta", property="og:description")
            og_img = soup.find("meta", property="og:image")

            title = (og_title["content"] if og_title else soup.title.string or "Link").strip()
            description = (og_desc["content"] if og_desc else "").strip()

            embed = {
                "$type": "app.bsky.embed.external",
                "external": {
                    "uri": url,
                    "title": title[:200],
                    "description": description[:1000]
                }
            }

            if og_img:
                blob = self._upload_blob(og_img["content"])
                if blob:
                    embed["external"]["thumb"] = blob

            return embed
        except Exception as e:
            print(f"Warning: Metadata scraping failed ({e}).")
            return None

    def post_text(self, text: str, create_card: bool = True):
        """Main method to post text with facets and an optional link card."""
        facets = self._find_url_facets(text)

        embed = None
        if create_card and facets:
            first_url = facets[0]["features"][0]["uri"]
            embed = self._get_external_embed(first_url)

        # Final check: Bluesky requires 'title' and 'uri' for a valid embed card
        if embed and (not embed["external"].get("title") or not embed["external"].get("uri")):
            embed = None

        payload = {
            "repo": self.did,
            "collection": "app.bsky.feed.post",
            "record": {
                "$type": "app.bsky.feed.post",
                "text": text,
                "facets": facets,
                "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "langs": ["en"]
            },
        }

        # Only add the embed key if we have a valid object
        if embed:
            payload["record"]["embed"] = embed

        url = f"{self.BASE_URL}/com.atproto.repo.createRecord"
        headers = {"Authorization": f"Bearer {self.access_jwt}"}

        response = requests.post(url, headers=headers, json=payload)

        if not response.ok:
            print(f"Debug Payload: {payload}")
            print(f"Error Response: {response.text}")

        response.raise_for_status()
        return response.json()


def main():
    file_path = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/posts/posts_dt.jsonl"
    delay_minutes = 2 # Time to wait before EACH post

    client = BlueskyClient()

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                # Parse the JSON line
                post_data = json.loads(line)
                post_content = post_data.get("text", "")
                print(len(post_content))

                if post_content:
                    # Apply delay before posting
                    if delay_minutes > 0:
                        print(f"⏳ Waiting {delay_minutes} minute(s) before next post...")
                        time.sleep(delay_minutes * 60)

                    print(f"🚀 Posting: {post_content[:50]}...")
                    result = client.post_text(post_content)
                    print(f"✅ Success! URI: {result['uri']}")

    except FileNotFoundError:
        print(f"❌ Error: The file '{file_path}' was not found.")
    except Exception as e:
        print(f"❌ Critical Error: {e}")


if __name__ == "__main__":
    main()
