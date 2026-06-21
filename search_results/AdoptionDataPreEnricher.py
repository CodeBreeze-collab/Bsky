import os
import json
import re
import requests
from bs4 import BeautifulSoup
from atproto import Client
from google import genai

class AdoptionDataPreEnricher:
    YOUTUBE_DOMAINS = ["youtube.com", "youtu.be"]

    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.bsky_handle = os.getenv("BSKY_HANDLE")
        self.bsky_password = os.getenv("BSKY_PASSWORD")

        if not self.api_key:
            raise ValueError("Missing GEMINI_API_KEY env variable")

        self.gemini_client = genai.Client(api_key=self.api_key)
        self.bsky_client = None
        if self.bsky_handle and self.bsky_password:
            self.bsky_client = Client()
            self.bsky_client.login(self.bsky_handle, self.bsky_password)

        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "AdoptionDataEnricher/1.0"})

    # -----------------------------
    # Bluesky Live Fetch
    # -----------------------------
    def fetch_live_post_data(self, post_url):
        if not self.bsky_client or "bsky.app" not in post_url:
            return {}
        try:
            parts = post_url.strip("/").split("/")
            handle, post_id = parts[-3], parts[-1]
            profile = self.bsky_client.get_profile(actor=handle)
            uri = f"at://{profile.did}/app.bsky.feed.post/{post_id}"
            response = self.bsky_client.app.bsky.feed.get_posts({'uris': [uri]})
            if not response.posts: return {}
            post = response.posts[0]

            extracted_data = {"text": getattr(post.record, 'text', ''), "embed": {}, "facets": []}

            if hasattr(post.embed, 'external'):
                extracted_data["embed"] = {
                    "$type": "app.bsky.embed.external",
                    "external": {
                        "uri": getattr(post.embed.external, 'uri', ''),
                        "title": getattr(post.embed.external, 'title', ''),
                        "description": getattr(post.embed.external, 'description', '')
                    }
                }

            if hasattr(post.record, 'facets') and post.record.facets:
                for f in post.record.facets:
                    extracted_data["facets"].append(f.to_dict() if hasattr(f, 'to_dict') else f)

            return extracted_data
        except Exception as e:
            print(f"[API Error]: {e}")
            return {}

    # -----------------------------
    # URL extraction from JSON recursively
    # -----------------------------
    def extract_urls_recursive(self, obj):
        urls = []
        if isinstance(obj, str):
            if obj.startswith("http"):
                urls.append(obj)
        elif isinstance(obj, dict):
            for v in obj.values():
                urls.extend(self.extract_urls_recursive(v))
        elif isinstance(obj, list):
            for i in obj:
                urls.extend(self.extract_urls_recursive(i))
        return list(set(urls))

    # -----------------------------
    # YouTube metadata
    # -----------------------------
    def get_youtube_metadata(self, url):
        try:
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            video_id = None
            if "youtu.be" in domain:
                video_id = parsed.path.strip("/")
            elif "youtube.com" in domain:
                if "/shorts/" in parsed.path:
                    video_id = parsed.path.split("/")[-1]
                else:
                    video_id = parse_qs(parsed.query).get("v", [None])[0]
            if not video_id: return None
            resp = self.session.get(f"https://www.youtube.com/watch?v={video_id}", timeout=5)
            soup = BeautifulSoup(resp.text, "html.parser")
            def get_meta(prop):
                tag = soup.find("meta", property=prop)
                return tag["content"] if tag else ""
            return {
                "video_id": video_id,
                "url": url,
                "title": get_meta("og:title"),
                "description": get_meta("og:description"),
                "thumbnail": get_meta("og:image"),
                "embed_url": f"https://www.youtube.com/embed/{video_id}"
            }
        except:
            return None

    # -----------------------------
    # Guess shelter URL from known domains
    # -----------------------------
    def guess_shelter_url(self, urls):
        shelter_domains = ["nycacc.org", "animalcarecenters.org", "aspca.org", "petfinder.com",
                           "hempsteadny.gov", "spca", "humane"]
        for url in urls:
            if any(sd in url.lower() for sd in shelter_domains): return url
        return ""

    # -----------------------------
    # LLM fallback using Gemini
    # -----------------------------
    def gemini_llm_fallback(self, pet_name, extra_context=""):
        """Use Gemini LLM to infer YouTube and shelter URLs in JSON format."""
        try:
            system_instructions = (
                "You are a data enrichment assistant. "
                "Receive JSONL posts with 'text' and optional 'extra_context'. "
                "Return ONLY JSON with 'youtube_urls' and 'shelter_urls'."
            )
            prompt = f"Pet name: {pet_name}\nExtra context: {extra_context}\nReturn JSON like {{'youtube_urls': [...], 'shelter_urls': [...]}}"
            response = self.gemini_client.models.generate_content(
                model="gemini-2.5-flash-lite",
                config={
                    "system_instruction": system_instructions,
                    "response_mime_type": "application/json",
                },
                contents=prompt
            )
            text = response.text.strip()
            if text.startswith("```"):
                text = "\n".join([l for l in text.splitlines() if not l.strip().startswith("```")])
            data = json.loads(text)
            return data.get("youtube_urls", []), data.get("shelter_urls", [])
        except Exception as e:
            print(f"[Gemini LLM Error]: {e}")
            return [], []

    # -----------------------------
    # Bluesky parent context
    # -----------------------------
    def get_bsky_parent_context(self, post_url):
        if not self.bsky_client or "bsky.app" not in post_url: return ""
        try:
            parts = post_url.strip("/").split('/')
            handle, post_id = parts[-3], parts[-1]
            profile = self.bsky_client.get_profile(actor=handle)
            uri = f"at://{profile.did}/app.bsky.feed.post/{post_id}"
            thread_res = self.bsky_client.app.bsky.feed.get_post_thread({'uri': uri, 'depth': 0, 'parentHeight': 1})
            parent = getattr(thread_res.thread, 'parent', None)
            if parent and hasattr(parent, 'post'):
                return getattr(parent.post.record, 'text', '')
        except: pass
        return ""

    def get_domain(self, url):
        try:
            from urllib.parse import urlparse
            return urlparse(url).netloc
        except:
            return ""

    # -----------------------------
    # Main enrichment
    # -----------------------------
    def enrich_file(self, input_file, output_file):
        with open(input_file, "r", encoding="utf-8") as f_in, \
             open(output_file, "w", encoding="utf-8") as f_out:

            for line in f_in:
                if not line.strip(): continue
                item = json.loads(line)
                post_url = item.get("post_url", "")
                print(f"\nProcessing: {post_url}")

                # 1. Extract URLs locally
                urls = self.extract_urls_recursive(item)
                source_stage = "local JSON"

                # 2. Fallback: live API
                if not urls and post_url:
                    print("  [Local empty]: Fetching live record...")
                    live_data = self.fetch_live_post_data(post_url)
                    urls = self.extract_urls_recursive(live_data)
                    if urls:
                        source_stage = "live API"

                # 3. Fallback: Gemini LLM
                shelter_urls = []
                if not urls and self.gemini_client:
                    pet_name_match = re.search(r'\b[A-Z][a-z]+\s?\d*\b', item.get("text", ""))
                    pet_name = pet_name_match.group(0) if pet_name_match else ""
                    if pet_name:
                        extra_context = self.get_bsky_parent_context(post_url)
                        print(f"  [No URLs yet]: Using Gemini LLM fallback for '{pet_name}'")
                        yt_urls, shelter_urls = self.gemini_llm_fallback(pet_name, extra_context)
                        urls.extend(yt_urls)
                        source_stage = "gemini LLM fallback"

                print(f"  [Found URLs] ({source_stage}): {urls}")

                # 4. Metadata & context
                parent_context = self.get_bsky_parent_context(post_url)
                link_context = ""
                if urls:
                    link_context = self.get_link_context(urls[0])
                shelter_url = self.guess_shelter_url(urls) or (shelter_urls[0] if shelter_urls else "")

                # 5. YouTube metadata
                youtube_videos = []
                for u in urls:
                    if any(dom in u.lower() for dom in self.YOUTUBE_DOMAINS):
                        meta = self.get_youtube_metadata(u)
                        if meta:
                            youtube_videos.append(meta)

                enriched = {
                    **item,
                    "urls": urls,
                    "shelter_url": shelter_url,
                    "source_domain": self.get_domain(post_url),
                    "shelter_domain": self.get_domain(shelter_url) if shelter_url else "",
                    "parent_context": parent_context,
                    "link_context": link_context,
                    "youtube_videos": youtube_videos
                }

                f_out.write(json.dumps(enriched) + "\n")

    def get_link_context(self, url):
        """Scrape title/description from link."""
        try:
            resp = self.session.get(url, timeout=5)
            if resp.status_code != 200: return ""
            soup = BeautifulSoup(resp.text, "html.parser")
            title = soup.title.string if soup.title else ""
            meta = soup.find("meta", {"name": "description"})
            desc = meta["content"] if meta else ""
            return f"[Link Content: {title} - {desc}]"
        except:
            return ""

    # -----------------------------
    # Run pipeline
    # -----------------------------
    def run(self, input_file, output_file):
        print("Starting enrichment pipeline...")
        self.enrich_file(input_file, output_file)
        print("Done.")

def main():
    # Read environment variables for input/output and Bluesky credentials
    input_file = os.getenv(
        "INPUT_JSONL",
        "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/search_results/raw/test_manual-yt-video.jsonl"
    )
    output_file = os.getenv(
        "OUTPUT_JSONL",
        "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/search_results/raw/test_manual-yt-video-enriched.jsonl"
    )

    enricher = AdoptionDataPreEnricher()
    enricher.run(input_file, output_file)


if __name__ == "__main__":
    main()