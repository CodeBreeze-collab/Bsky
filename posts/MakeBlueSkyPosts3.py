import os
import re
import json
import time
import requests
import cloudscraper
from enum import Enum
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# --- CONFIGURATION ---
DELAY_MINUTES = 1


class Channel(Enum):
    NE_NEWS = "ne_news"
    DT_NEWS = "dt_news"
    S_NEWS = "s_news"
    STRANGER_NEWS = "stranger_news"
    V_SEARCH = "v_search"
    PE_NEWS = "pe_news"
    STALKING_NEWS = "stalking_news"


class BlueskyClient:
    BASE_URL = "https://bsky.social/xrpc"

    def __init__(self, handle, app_password):
        self.handle = handle
        self.app_password = app_password
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

    def _build_facets(self, text: str, links: list | None, tags: list | None):
        facets = []

        text_bytes = text.encode("utf-8")
        text_len = len(text_bytes)

        def find_all_bytes(haystack: bytes, needle: bytes):
            start = 0
            while True:
                idx = haystack.find(needle, start)
                if idx == -1:
                    return
                yield idx, idx + len(needle)
                start = idx + len(needle)

        used_ranges = []

        def overlaps(a_start, a_end):
            for b_start, b_end in used_ranges:
                if not (a_end <= b_start or a_start >= b_end):
                    return True
            return False

        # --- LINKS (prefer last occurrence) ---
        for url in links or []:
            url_bytes = url.encode("utf-8")
            matches = list(find_all_bytes(text_bytes, url_bytes))
            if not matches:
                continue

            start, end = matches[-1]

            if end > text_len or overlaps(start, end):
                continue

            facets.append({
                "index": {"byteStart": start, "byteEnd": end},
                "features": [{
                    "$type": "app.bsky.richtext.facet#link",
                    "uri": url
                }]
            })
            used_ranges.append((start, end))

        # --- HASHTAGS (prefer last occurrence) ---
        for tag in tags or []:
            full_tag = f"#{tag}"
            tag_bytes = full_tag.encode("utf-8")
            matches = list(find_all_bytes(text_bytes, tag_bytes))
            if not matches:
                continue

            start, end = matches[-1]

            if end > text_len or overlaps(start, end):
                continue

            facets.append({
                "index": {"byteStart": start, "byteEnd": end},
                "features": [{
                    "$type": "app.bsky.richtext.facet#tag",
                    "tag": tag
                }]
            })
            used_ranges.append((start, end))

        # Sort by byteStart for Bluesky sanity
        facets.sort(key=lambda f: f["index"]["byteStart"])

        return facets

    def _upload_blob(self, image_url: str):
        try:
            img_res = self.scraper.get(image_url, timeout=10)
            img_res.raise_for_status()
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
        try:
            # --- Special handling for YouTube ---
            if "youtube.com/watch" in url or "youtu.be/" in url:
                try:
                    oembed_url = f"https://www.youtube.com/oembed?url={url}&format=json"
                    res = requests.get(oembed_url, timeout=10)
                    res.raise_for_status()
                    data = res.json()
                    thumb_blob = self._upload_blob(data.get("thumbnail_url")) if data.get("thumbnail_url") else None
                    return {
                        "$type": "app.bsky.embed.external",
                        "external": {
                            "uri": url,
                            "title": data.get("title", "")[:200],
                            "description": data.get("author_name", "")[:1000],
                            **({"thumb": thumb_blob} if thumb_blob else {})
                        }
                    }
                except Exception as e:
                    print(f"❌ YouTube oEmbed error: {e}")
                    return None

            # --- Fallback for other links ---
            res = self.scraper.get(url, timeout=15)
            res.raise_for_status()
            soup = BeautifulSoup(res.text, "html.parser")
            og_title = soup.find("meta", property="og:title")
            og_desc = soup.find("meta", property="og:description")
            og_img = soup.find("meta", property="og:image")

            title = (og_title["content"].strip() if og_title else None)
            description = (og_desc["content"].strip() if og_desc else "")
            if not title: return None

            embed = {
                "$type": "app.bsky.embed.external",
                "external": {"uri": url, "title": title[:200], "description": description[:1000]}
            }

            if og_img and og_img.get("content"):
                blob = self._upload_blob(og_img["content"])
                if blob: embed["external"]["thumb"] = blob
            return embed

        except Exception as e:
            print(f"❌ [EMBED] Error: {e}")
            return None

    def post_text(self, text: str, links: list = None, tags: list = None):
        """
        Processes text, ensures the URL is appended to the body,
        auto-appends missing hashtags, builds rich-text facets,
        and posts to Bluesky.
        """

        # 1. Ensure the URL is actually in the text body
        # Bluesky won't show the link unless it's part of the 'text' string
        if links:
            primary_link = links[0]
            if primary_link not in text:
                # Add two newlines for a clean look before the URL
                text = text.rstrip() + "\n\n" + primary_link

        # 2. Handle Tag Appending
        if tags:
            missing_tags = [t for t in tags if f"#{t}" not in text]
            if missing_tags:
                # If we just added a link, we can just space the tags out after it
                # Otherwise, add the double newline
                text = text.rstrip() + "\n\n" + " ".join([f"#{t}" for t in missing_tags])

        # 3. Build facets using the FINAL version of the text
        # This must happen AFTER the text is fully assembled
        facets = self._build_facets(text, links, tags)

        # 4. Handle Link Embeds (The Preview Card)
        embed = None
        if links:
            # Generate the visual card (title, description, thumbnail)
            embed = self._get_external_embed(links[0])

        # 5. Construct the AT Protocol Payload
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

        if embed:
            payload["record"]["embed"] = embed

        # 6. Send to Bluesky
        url = f"{self.BASE_URL}/com.atproto.repo.createRecord"
        headers = {"Authorization": f"Bearer {self.access_jwt}"}

        print(f"[BLUESKY POST] POST {url}\nPayload:\n{json.dumps(payload, indent=2)}")

        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()

        return response.json()

# BLUESKY_HANDLE_ne_news=newenglandtopnews.bsky.social;BLUESKY_APP_PASSWORD_ne_news=3jfu-6ql5-rr5x-c7sf;BLUESKY_HANDLE_dt_news=denouncethis.bsky.social;BLUESKY_APP_PASSWORD_dt_news=epxo-ikyy-4hhl-i6yb;BLUESKY_HANDLE_s_news=scamshield.bsky.social;BLUESKY_APP_PASSWORD_s_news=rh2d-qqm5-k4mq-bhms;BLUESKY_HANDLE_v_search=vegansearchengine.bsky.social;BLUESKY_APP_PASSWORD_v_search=px6u-e35r-ryay-qkxs;BLUESKY_HANDLE_stranger_news=strangerhappenings.bsky.social;BLUESKY_APP_PASSWORD_stranger_news=i4dq-d4ze-gash-ab7q;BLUESKY_HANDLE_pe_news=policyevidence.bsky.social;BLUESKY_APP_PASSWORD_pe_news=x7x4-44dr-k5gk-b2s4;BLUESKY_HANDLE_stalking_news=stalking-alerts.bsky.social
def pre_flight_check(file_path, target_channel: Channel):
    load_dotenv()

    t_id = target_channel.value
    h_key, p_key = f"BLUESKY_HANDLE_{t_id}", f"BLUESKY_APP_PASSWORD_{t_id}"

    handle = os.getenv(h_key)
    password = os.getenv(p_key)

    if not handle or not password:
        print(f"❌ Error: Missing env variables {h_key} or {p_key}")
        return None, None

    try:
        client = BlueskyClient(handle, password)
    except Exception as e:
        print(f"❌ Login failed: {e}")
        return None, None

    valid_posts = []
    if not os.path.exists(file_path):
        print(f"❌ Error: File {file_path} does not exist")
        return None, None

    with open(file_path, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                if data.get("channel") == t_id:
                    post = {
                        "text": (data.get("text") or "").strip(),
                        "links": data.get("links", []),
                        "tags": data.get("tags", [])
                    }
                    valid_posts.append(post)

                    # ✅ Print the post info
                    print(f"\nPost #{len(valid_posts)}:")
                    print(f"Text: {post['text']}")
                    print(f"Links: {post['links']}")
                    print(f"Hashtags: {post['tags']}")

            except Exception as e:
                print(f"⚠️ Skipping malformed line {i}: {e}")

    return client, valid_posts



def run_posting_sequence(client, posts):
    print(f"🚀 Starting posting sequence for {len(posts)} items...")
    for i, post_data in enumerate(posts, 1):
        print(f"⏳ Waiting {DELAY_MINUTES} minutes...", flush=True)
        time.sleep(10)
        try:
            client.post_text(post_data["text"], links=post_data["links"], tags=post_data["tags"])
            print(f"✅ Posted {i}/{len(posts)}")
        except Exception as e:
            print(f"❌ Failed: {e}")


if __name__ == "__main__":
    FILE_PATH = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/my_posts/stalking-2025-05-22.jsonl"
    client, posts = pre_flight_check(FILE_PATH, Channel.STALKING_NEWS)
    print("Here")
    if not client:
        print("❌ Client not initialized. Check env vars and login.")
    if posts is None:
        print("❌ Posts list is None. Check the JSONL file path.")
    elif not posts:
        print("⚠️ No valid posts found for this channel.")

    if client and posts:
        run_posting_sequence(client, posts)
    else:
        print("💤 Exiting: nothing to post.")
