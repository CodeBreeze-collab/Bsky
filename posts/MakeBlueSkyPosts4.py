import requests
import cloudscraper
from bs4 import BeautifulSoup
from enum import Enum
from datetime import datetime, timezone
import json
import os
from dotenv import load_dotenv
from PIL import Image
from io import BytesIO


class FacetPolicy(Enum):
    EMBED_ONLY = "embed_only"     # Embed card, NO link facet
    FACET_ONLY = "facet_only"     # Link facet, NO embed
    TEXT_ONLY = "text_only"       # URL in text only, no facet, no embed

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

    # --- URL expansion ---
    @staticmethod
    def expand_url(url: str, timeout=10) -> str:
        try:
            res = requests.head(url, allow_redirects=True, timeout=timeout)
            if res.ok and res.url:
                return res.url
        except Exception:
            pass
        return url

    # --- Facet builder ---
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

        # Links
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
                "features": [{"$type": "app.bsky.richtext.facet#link", "uri": url}]
            })
            used_ranges.append((start, end))

        # Hashtags
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
                "features": [{"$type": "app.bsky.richtext.facet#tag", "tag": tag}]
            })
            used_ranges.append((start, end))

        facets.sort(key=lambda f: f["index"]["byteStart"])
        return facets

    MAX_BLOB_SIZE = 976_560

    def _upload_blob(self, image_url: str, max_blob_size=None):
        MAX_BLOB_SIZE = max_blob_size or self.MAX_BLOB_SIZE
        try:
            img_res = self.scraper.get(image_url, timeout=10)
            img_res.raise_for_status()
            content = img_res.content

            # Skip or compress if too large
            if len(content) > MAX_BLOB_SIZE:
                try:
                    img = Image.open(BytesIO(content))
                    buf = BytesIO()
                    quality = 85
                    while True:
                        img.save(buf, format="JPEG", quality=quality)
                        if buf.getbuffer().nbytes <= MAX_BLOB_SIZE or quality <= 10:
                            break
                        quality -= 5
                        buf.seek(0)
                        buf.truncate(0)
                    content = buf.getvalue()
                    print(f"⚠️ Compressed image to {len(content) / 1024:.1f} KB")
                except Exception as e:
                    print(f"⚠️ Could not compress image: {e}, skipping thumbnail")
                    return None

            headers = {
                "Authorization": f"Bearer {self.access_jwt}",
                "Content-Type": img_res.headers.get("Content-Type", "image/jpeg")
            }
            url = f"{self.BASE_URL}/com.atproto.repo.uploadBlob"
            res = requests.post(url, headers=headers, data=content)
            res.raise_for_status()
            return res.json()["blob"]

        except Exception as e:
            print(f"  > Thumbnail upload skipped: {e}")
            return None

    # --- Get external embed card ---
    def _get_external_embed(self, url: str):
        try:
            # YouTube special handling
            if "youtube.com/watch" in url or "youtu.be/" in url:
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

            # Fallback for other links
            res = self.scraper.get(url, timeout=15)
            res.raise_for_status()
            soup = BeautifulSoup(res.text, "html.parser")
            og_title = soup.find("meta", property="og:title")
            og_desc = soup.find("meta", property="og:description")
            og_img = soup.find("meta", property="og:image")

            title = (og_title["content"].strip() if og_title else None)
            description = (og_desc["content"].strip() if og_desc else "")
            if not title: return None

            embed = {"$type": "app.bsky.embed.external", "external": {"uri": url, "title": title[:200], "description": description[:1000]}}

            if og_img and og_img.get("content"):
                blob = self._upload_blob(og_img["content"])
                if blob: embed["external"]["thumb"] = blob
            return embed

        except Exception as e:
            print(f"❌ [EMBED] Error: {e}")
            return None

    # --- Validation before posting ---
    @staticmethod
    def validate_post(text, facets, embed, policy: FacetPolicy):
        errors = []
        if not text.strip():
            errors.append("Post text is empty")
        if len(text.encode("utf-8")) > 3000:
            errors.append("Post exceeds 3000 UTF-8 bytes")

        link_facets = [
            f for f in facets
            if any(feat["$type"] == "app.bsky.richtext.facet#link"
                   for feat in f["features"])
        ]
        if embed and link_facets and policy == FacetPolicy.EMBED_ONLY:
            errors.append("Embed + link facet present (not allowed)")

        if embed and "external" not in embed:
            errors.append("Invalid embed object")

        for f in facets:
            idx = f["index"]
            if idx["byteStart"] >= idx["byteEnd"]:
                errors.append("Facet byteStart >= byteEnd")

        return errors

    # --- Main post_text ---
    def post_text(
            self,
            text: str,
            links: list[str] | None = None,
            tags: list[str] | None = None,
            facet_policy: FacetPolicy = FacetPolicy.EMBED_ONLY,
            dry_run: bool = False
    ):
        links = links or []
        tags = tags or []

        # --- Step 1: Prepare text link ---
        # Keep TinyURL in post text to stay under 300 graphemes
        primary_text_link = links[0] if links else None
        if primary_text_link and primary_text_link not in text:
            text = text.rstrip() + "\n\n" + primary_text_link

        # Append missing hashtags
        missing_tags = [t for t in tags if f"#{t}" not in text]
        if missing_tags:
            text = text.rstrip() + "\n\n" + " ".join(f"#{t}" for t in missing_tags)

        # --- Step 2: Build facets ---
        facet_links = links if facet_policy == FacetPolicy.FACET_ONLY else []
        facets = self._build_facets(text, facet_links, tags)

        # --- Step 3: Build embed using expanded URL ---
        embed = None
        if facet_policy == FacetPolicy.EMBED_ONLY and primary_text_link:
            expanded_url = self.expand_url(primary_text_link)
            embed = self._get_external_embed(expanded_url)

        # --- Step 4: Validation ---
        errors = self.validate_post(text, facets, embed, facet_policy)
        if errors:
            print("❌ Validation failed:")
            for e in errors:
                print("  •", e)
            if dry_run:
                return None
            raise ValueError("Post validation failed")

        # --- Step 5: Construct payload ---
        payload = {
            "repo": self.did,
            "collection": "app.bsky.feed.post",
            "record": {
                "$type": "app.bsky.feed.post",
                "text": text,
                "facets": facets,
                "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "langs": ["en"]
            }
        }

        if embed:
            payload["record"]["embed"] = embed

        print(f"[BLUESKY POST] Payload:\n{json.dumps(payload, indent=2)}")

        if dry_run:
            print("🧪 Dry-run mode: post not sent")
            return payload

        # --- Step 6: Send to Bluesky ---
        url = f"{self.BASE_URL}/com.atproto.repo.createRecord"
        headers = {"Authorization": f"Bearer {self.access_jwt}"}
        res = requests.post(url, headers=headers, json=payload)
        if not res.ok:
            print("❌ Bluesky error:", res.text)
        res.raise_for_status()
        return res.json()


class Channel(Enum):
    NE_NEWS = "ne_news"
    DT_NEWS = "dt_news"
    S_NEWS = "s_news"
    STRANGER_NEWS = "stranger_news"
    V_SEARCH = "v_search"
    PE_NEWS = "pe_news"


def pre_flight_check(file_path, target_channel: Channel):
    """
    Validates environment variables, authenticates with Bluesky,
    and parses the JSONL file for specific channel posts.
    """
    # 1. Load Environment Variables
    load_dotenv()

    t_id = target_channel.value
    h_key = f"BLUESKY_HANDLE_{t_id}"
    p_key = f"BLUESKY_APP_PASSWORD_{t_id}"

    handle = os.getenv(h_key)
    password = os.getenv(p_key)

    # 2. Detailed Variable Validation
    missing_vars = []
    if not handle:
        missing_vars.append(h_key)
    if not password:
        missing_vars.append(p_key)

    if missing_vars:
        print(f"❌ CRITICAL: Missing environment variables: {', '.join(missing_vars)}")
        print(f"   Ensure these are defined in your .env file.")
        return None, None

    # 3. Client Initialization & Authentication
    print(f"🔐 Attempting to authenticate handle: {handle}...")
    try:
        client = BlueskyClient(handle, password)
        print(f"✅ Authentication successful for {handle}")
    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code
        try:
            error_json = e.response.json()
            error_msg = error_json.get("message", "No error message provided")
        except:
            error_msg = e.response.text

        print(f"❌ Login failed ({status_code}): {error_msg}")
        if status_code == 401:
            print("   TIP: Verify your App Password (not your account password) and handle format.")
        return None, None
    except Exception as e:
        print(f"❌ Unexpected error during login: {type(e).__name__}: {e}")
        return None, None

    # 4. File Path Validation
    abs_path = os.path.abspath(file_path)
    if not os.path.exists(abs_path):
        print(f"❌ File not found: {abs_path}")
        return client, None

    # 5. JSONL Parsing
    valid_posts = []
    print(f"📂 Reading posts from: {abs_path}...")

    try:
        with open(abs_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f, 1):
                clean_line = line.strip()
                if not clean_line:
                    continue

                try:
                    data = json.loads(clean_line)
                    # Only grab posts matching the requested channel
                    if data.get("channel") == t_id:
                        post = {
                            "text": (data.get("text") or "").strip(),
                            "links": data.get("links", []),
                            "tags": data.get("tags", [])
                        }

                        # Basic validation of the post structure
                        if post["text"]:
                            valid_posts.append(post)
                            print(f"📊 Valid Post: {post}")
                        else:
                            print(f"⚠️ Warning: Post on line {i} has no text. Skipping.")

                except json.JSONDecodeError:
                    print(f"⚠️ Skipping malformed JSON on line {i}")
                except Exception as e:
                    print(f"⚠️ Error processing line {i}: {e}")

        print(f"📊 Found {len(valid_posts)} valid posts for channel '{t_id}'.")
        return client, valid_posts

    except Exception as e:
        print(f"❌ Failed to read or parse file: {e}")
        return client, None

# --- Run posting sequence ---
import time

DELAY_MINUTES = 2  # adjust if you want a delay between posts

def run_posting_sequence(client: BlueskyClient, posts, facet_policy: FacetPolicy = FacetPolicy.EMBED_ONLY, dry_run=False):
    print(f"🚀 Starting posting sequence for {len(posts)} posts...")

    for i, post_data in enumerate(posts, 1):
        print(f"\n⏳ Waiting {DELAY_MINUTES} minutes before post {i}...", flush=True)
        time.sleep(DELAY_MINUTES * 60)

        try:
            client.post_text(
                post_data["text"],
                links=post_data["links"],
                tags=post_data["tags"],
                facet_policy=facet_policy,
                dry_run=dry_run
            )
            print(f"✅ Posted {i}/{len(posts)}")
        except Exception as e:
            print(f"❌ Failed to post {i}: {e}")


class Channel(Enum):
    NE_NEWS = "ne_news"
    DT_NEWS = "dt_news"
    S_NEWS = "s_news"
    STRANGER_NEWS = "stranger_news"
    V_SEARCH = "v_search"
    PE_NEWS = "pe_news"

if __name__ == "__main__":
    FILE_PATH = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/posts/posts_ne_news.jsonl"
    client, posts = pre_flight_check(FILE_PATH, Channel.NE_NEWS)

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

