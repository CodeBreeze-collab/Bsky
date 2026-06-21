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


class Channel(Enum):
    NE_NEWS = "ne_news"
    DT_NEWS = "dt_news"
    S_NEWS = "s_news"
    STRANGER_NEWS = "stranger_news"
    V_SEARCH = "v_search"
    PE_NEWS = "pe_news"


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

    def _find_url_facets(self, text: str):
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
        print(f"\n🔎 [EMBED] Fetching OG metadata for: {url}")
        try:
            res = self.scraper.get(
                url,
                timeout=15,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}
            )
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

    def post_text(self, text: str):
        facets = self._find_url_facets(text)
        embed = None
        if facets:
            first_url = facets[0]["features"][0]["uri"]
            embed = self._get_external_embed(first_url)

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
        if embed: payload["record"]["embed"] = embed

        url = f"{self.BASE_URL}/com.atproto.repo.createRecord"
        headers = {"Authorization": f"Bearer {self.access_jwt}"}
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()


def audit_and_run(file_path, target_channel: Channel):
    load_dotenv()
    t_id = target_channel.value

    # 1. Fetch and Debug Credentials
    h_key, p_key = f"BLUESKY_HANDLE_{t_id}", f"BLUESKY_APP_PASSWORD_{t_id}"
    handle = os.getenv(h_key)
    password = os.getenv(p_key)

    print(f"--- Environment Check ---")
    print(f"🔑 Target Keys: {h_key} / {p_key}")
    print(f"👤 Handle Found: {handle if handle else 'MISSING'}")
    if password:
        masked_pass = f"{password[:4]}****{password[-4:]}" if len(password) > 8 else "****"
        print(f"🔐 Password Loaded: {masked_pass}")
    else:
        print(f"🔐 Password Loaded: MISSING")
    print(f"-------------------------\n")

    if not handle or not password:
        print(f"❌ Aborting: Credentials not found for channel {t_id}")
        return

    # 2. Immediate Login Check
    try:
        print(f"📡 Attempting login for {handle}...")
        client = BlueskyClient(handle, password)
        print("✅ Login successful! Proceeding to audit...")
    except requests.exceptions.HTTPError as e:
        print(f"❌ Login Failed: {e}")
        if e.response.status_code == 401:
            print(f"💡 Hint: Unauthorized. Check if '{p_key}' is a fresh App Password.")
        return
    except Exception as e:
        print(f"❌ Unexpected Error: {e}")
        return

    # 3. Audit
    posts = []
    errors = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f, 1):
                if not line.strip(): continue

                data = json.loads(line)
                text = (data.get("text") or data.get(",text") or "").strip()

                if data.get("channel") != t_id:
                    errors.append(f"Line {i}: Channel mismatch")
                if not text:
                    errors.append(f"Line {i}: Empty text")
                if len(text) > 300:
                    errors.append(f"Line {i}: Too long")

                channel = data.get("channel")
                print(f"⏳ Channel: {channel} ")
                print(f"⏳ Text: {text} ")
                print(f"⏳ Waiting {DELAY_MINUTES} minutes before Posting ...")
                time.sleep(DELAY_MINUTES * 60)

                posts.append(text)
    except Exception as e:
        print(f"❌ File Error: {e}")
        return

    if errors:
        print("❌ Audit failed:")
        for e in errors: print(f"  - {e}")
        return

    # 4. Final Post
    print(f"🚀 Audit passed. Posting {len(posts)} items...")
    for t in posts:
        client.post_text(t)
        time.sleep(2)


DELAY_MINUTES = 2

if __name__ == "__main__":
    FILE_PATH = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/posts/posts_dt.jsonl"
    audit_and_run(FILE_PATH, Channel.DT_NEWS)