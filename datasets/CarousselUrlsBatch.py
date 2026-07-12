import os
import json
import re
from datetime import datetime
import requests


class BlueskyDataEnricher:
    """
    A batch processor that traverses date-sorted directories of Bluesky datasets,
    evaluates text for context markers, and fetches un-truncated links and image
    carousel arrays via a single live API request per post.
    """

    BSKY_BASE_URL = "https://public.api.bsky.app/xrpc"

    def __init__(self, input_dir: str, output_dir: str, target_filename: str = "animal_centric_posts-w-loc-2.jsonl"):
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.target_filename = target_filename

        # Unified cache mapping post_url -> {"internal_urls": [...], "carousel_urls": [...]}
        # Saves network roundtrips for duplicate post lookups
        self._post_cache = {}

    def _parse_date_dir(self, dirname: str) -> datetime:
        try:
            return datetime.strptime(dirname, "%m-%d-%Y")
        except ValueError:
            return None

    def _get_sorted_date_dirs(self) -> list:
        dirs = []
        if not os.path.exists(self.input_dir):
            return dirs
        for name in os.listdir(self.input_dir):
            path = os.path.join(self.input_dir, name)
            if os.path.isdir(path):
                dt = self._parse_date_dir(name)
                if dt:
                    dirs.append((dt, path))
        dirs.sort(key=lambda x: x[0], reverse=True)
        return dirs

    def _collect_text(self, obj) -> list:
        """Recursively gather all human-readable string values out of a nested structure."""
        texts = []
        if isinstance(obj, dict):
            for v in obj.values():
                if isinstance(v, str):
                    texts.append(v)
                else:
                    texts.extend(self._collect_text(v))
        elif isinstance(obj, list):
            for item in obj:
                texts.extend(self._collect_text(item))
        return texts

    def _check_for_pledges(self, text: str) -> bool:
        text_lower = text.lower()
        return "pledge" in text_lower or "$" in text_lower or "dollar" in text_lower

    def _resolve_handle_to_did(self, handle: str) -> str:
        try:
            endpoint = f"{self.BSKY_BASE_URL}/com.atproto.identity.resolveHandle"
            resp = requests.get(endpoint, params={"handle": handle}, timeout=5)
            if resp.status_code == 200:
                return resp.json().get("did")
        except Exception:
            pass
        return None

    def _normalize_to_at_uri(self, url: str) -> str:
        match = re.search(r"https://bsky\.app/profile/([^/]+)/post/([^/]+)", url)
        if not match:
            return None
        handle_or_did, rkey = match.groups()
        if not handle_or_did.startswith("did:"):
            did = self._resolve_handle_to_did(handle_or_did)
            if not did:
                return None
        else:
            did = handle_or_did
        return f"at://{did}/app.bsky.feed.post/{rkey}"

    def _fetch_post_enrichment(self, post_url: str) -> dict:
        """
        Hits the AppView network once to extract both full URLs (facets/embeds)
        and all raw carousel image locations (standalone layouts or nested media items).
        """
        if not post_url:
            return {"internal_urls": [], "carousel_urls": []}

        if post_url in self._post_cache:
            return self._post_cache[post_url]

        enrichment_data = {"internal_urls": [], "carousel_urls": []}

        try:
            at_uri = self._normalize_to_at_uri(post_url)
            if not at_uri:
                return enrichment_data

            endpoint = f"{self.BSKY_BASE_URL}/app.bsky.feed.getPosts"
            resp = requests.get(endpoint, params={"uris": [at_uri]}, timeout=8)

            if resp.status_code == 200:
                data = resp.json()
                posts = data.get("posts", [])
                if posts:
                    post = posts[0]
                    record = post.get("record", {})

                    # 1. Gather outbound text anchor facets
                    facets = record.get("facets", [])
                    for facet in facets:
                        for feature in facet.get("features", []):
                            if feature.get("$type") == "app.bsky.richtext.facet#link":
                                uri = feature.get("uri")
                                if uri and uri not in enrichment_data["internal_urls"]:
                                    enrichment_data["internal_urls"].append(uri)

                    # 2. Gather outbound link preview card details
                    embed = post.get("embed", {})
                    if embed.get("$type") == "app.bsky.embed.external#view":
                        external_uri = embed.get("external", {}).get("uri")
                        if external_uri and external_uri not in enrichment_data["internal_urls"]:
                            enrichment_data["internal_urls"].append(external_uri)

                    # 3. Pull image assets out of standard or layout carousel structures
                    embed_type = embed.get("$type", "")

                    # Unwrap media components if hidden inside a record-with-media combo asset
                    media_block = embed if embed_type != "app.bsky.embed.recordWithMedia#view" else embed.get("media",
                                                                                                              {})
                    actual_type = media_block.get("$type", "")

                    if actual_type == "app.bsky.embed.images#view":
                        for img_obj in media_block.get("images", []):
                            fullsize_url = img_obj.get("fullsize")
                            if fullsize_url and fullsize_url not in enrichment_data["carousel_urls"]:
                                enrichment_data["carousel_urls"].append(fullsize_url)

                    elif actual_type == "app.bsky.embed.gallery#view":
                        for item_obj in media_block.get("items", []):
                            fullsize_url = item_obj.get("fullsize")
                            if fullsize_url and fullsize_url not in enrichment_data["carousel_urls"]:
                                enrichment_data["carousel_urls"].append(fullsize_url)

        except Exception as e:
            print(f"      [Warning] Could not extract live data for {post_url}: {e}")

        # Protect against failures or deleted entries looping back across the pipe
        self._post_cache[post_url] = enrichment_data
        return enrichment_data

    def process_file(self, input_file: str, output_file: str):
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        processed = 0
        pledge_count = 0

        with open(input_file, "r", encoding="utf-8") as infile, \
                open(output_file, "w", encoding="utf-8") as outfile:

            for line in infile:
                if not line.strip():
                    continue

                record = json.loads(line)

                # Text validation for pledge tagging
                combined_text = "\n".join(self._collect_text(record))
                has_pledge = self._check_for_pledges(combined_text)
                record["has_pledge"] = has_pledge

                if has_pledge:
                    pledge_count += 1

                # Locate the reference post URL tracking address
                target_url = record.get("post_url")
                if not target_url and record.get("associated_posts"):
                    target_url = record["associated_posts"][0].get("post_url")

                # Perform the unified API lookup extraction
                enrichment = self._fetch_post_enrichment(target_url)
                record["internal_urls"] = enrichment["internal_urls"]
                record["carousel_urls"] = enrichment["carousel_urls"]

                outfile.write(json.dumps(record, ensure_ascii=False) + "\n")
                processed += 1

        print(f"   Done: processed={processed}, found {pledge_count} posts with pledges.")

    def run(self):
        """Starts processing the defined execution directories block by block."""
        date_dirs = self._get_sorted_date_dirs()
        if not date_dirs:
            print(f"No valid chronological date folders located inside: {self.input_dir}")
            return

        for dt, date_dir in date_dirs:
            print(f"\nProcessing target date frame: {dt.strftime('%m-%d-%Y')}")

            for root, _, files in os.walk(date_dir):
                for filename in files:
                    if filename != self.target_filename:
                        continue

                    input_file = os.path.join(root, filename)
                    relative = os.path.relpath(root, self.input_dir)
                    output_file = os.path.join(self.output_dir, relative, filename)

                    print(f"   Reading: {input_file}")
                    self.process_file(input_file, output_file)


if __name__ == "__main__":
    # Configure your file pathing paths
    INPUT_PATH = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/needs_help_v2_/v3_corrected/composite_output"
    OUTPUT_PATH = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/needs_help_v2_/v3_corrected/composite_output_w_carousel"

    # Initialize processor
    enricher = BlueskyDataEnricher(
        input_dir=INPUT_PATH,
        output_dir=OUTPUT_PATH
    )

    # Fire processing pipeline
    enricher.run()