import json
import re
import os
import time

import requests
from bs4 import BeautifulSoup
from google import genai
from atproto import Client

NEEDS_HELP_ = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/needs_help/"


# Note: You will need to install atproto, requests, and beautifulsoup4
# pip install atproto requests beautifulsoup4

class AdoptionDataEnricher:
    def __init__(self, api_key, bsky_handle=None, bsky_password=None):
        self.client = genai.Client(api_key=api_key)
        self.bsky_client = None

        # Initialize Bluesky client if credentials provided
        if bsky_handle and bsky_password:
            self.bsky_client = Client()
            self.bsky_client.login(bsky_handle, bsky_password)

    def _get_link_context(self, url):
        """Pass 1b: Scrape titles/descriptions from shared links."""
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) VeevaSearchBot/1.0'}
            response = requests.get(url, headers=headers, timeout=5)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                title = soup.title.string if soup.title else ""
                meta_desc = soup.find("meta", {"name": "description"})
                desc = meta_desc['content'] if meta_desc else ""
                return f"[Link Content: {title} - {desc}]"
        except Exception:
            return ""
        return ""

    def _get_bsky_parent_context(self, post_url):
        """Pass 1a: Fetch parent/root post if this is a reply or repost."""
        if not self.bsky_client or "bsky.app" not in post_url:
            return ""

        try:
            # 1. Parse out handle and post ID safely
            parts = post_url.strip("/").split('/')
            if len(parts) < 3:
                return ""

            handle = parts[-3]
            post_id = parts[-1]

            # 2. Resolve handle to DID
            profile = self.bsky_client.get_profile(actor=handle)
            uri = f"at://{profile.did}/app.bsky.feed.post/{post_id}"

            # 3. Fetch the thread
            # Set depth=0 because we only care about the parent of the current post
            thread_res = self.bsky_client.app.bsky.feed.get_post_thread({'uri': uri, 'depth': 0, 'parentHeight': 1})

            # 4. Defensive Check: Is this a valid thread view?
            thread_view = thread_res.thread

            # Check if parent exists and is not a 'NotFoundPost' or 'BlockedPost'
            if hasattr(thread_view, 'parent') and thread_view.parent is not None:
                # Some parent objects are 'NotFoundPost' or 'BlockedPost' which have no .post
                if hasattr(thread_view.parent, 'post'):
                    parent_record = thread_view.parent.post.record
                    return f"[Parent Post Context: {parent_record.text}]"

            return ""  # No parent or parent is inaccessible

        except Exception as e:
            # Silently fail or log for debugging
            # print(f"Context retrieval skipped for {post_url}: {e}")
            return ""

    def clean_llm_output(self, text):
        text = text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)
        return text

    def process_batch(self, batch, system_instructions, f_out):
        enriched_batch = []
        original_data_map = {}

        # 1. Prepare Batch
        for line in batch:
            try:
                item = json.loads(line)
                post_url = item.get('post_url', '')
                if not post_url: continue
                original_data_map[post_url] = item

                parent_context = self._get_bsky_parent_context(post_url)
                urls = re.findall(r'(https?://\S+)', item.get('text', ''))
                link_context = self._get_link_context(urls[0]) if urls else ""

                enriched_batch.append({
                    "post_url": post_url,
                    "text": item.get('text', ''),
                    "extra_context_for_ai": f"{parent_context} {link_context}".strip()
                })
            except json.JSONDecodeError:
                continue

        if not enriched_batch: return

        # 2. Call Gemini
        raw_input = "\n".join([json.dumps(i) for i in enriched_batch])
        try:
            print(f"--- Sending {len(enriched_batch)} items to Gemini ---")
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",  # Updated to a stable version
                config={
                    "system_instruction": system_instructions,
                    "response_mime_type": "application/json",
                },
                contents=raw_input,
            )
            raw_response_text = response.text
            cleaned = self.clean_llm_output(raw_response_text)

            # --- LOGGING TO FOLDER ---
            batch_id = f"batch_{int(time.time())}"
            log_dir = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/search_results/location_tagged/gemini_logs"
            os.makedirs(log_dir, exist_ok=True)

            with open(os.path.join(log_dir, f"{batch_id}_raw.txt"), "w") as f:
                f.write(raw_response_text)

            print(f"DEBUG: Saved AI response to {log_dir}/{batch_id}_raw.txt")
            # -------------------------

        except Exception as e:
            print(f"❌ Gemini API Request failed: {e}")
            return

        # 3. Parse and Merge (Hardened)
        lines_to_process = []
        try:
            # Attempt 1: Parse as a single JSON array (Standard for response_mime_type)
            try:
                parsed_data = json.loads(cleaned)
                if isinstance(parsed_data, list):
                    lines_to_process = parsed_data
                else:
                    lines_to_process = [parsed_data]
            except json.JSONDecodeError:
                # Attempt 2: Fallback for JSONL-style line-by-line responses
                print("⚠️ Warning: Response was not a valid JSON array. Attempting line-by-line parse.")
                for line in cleaned.splitlines():
                    if line.strip():
                        try:
                            lines_to_process.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue  # Skip individual unparseable lines

            # Proceed with merging the data we managed to extract
            success_count = 0
            for ai_output in lines_to_process:
                if not isinstance(ai_output, dict): continue

                url_key = ai_output.get('post_url')
                if url_key in original_data_map:
                    # Merge into a copy of original data to preserve original fields
                    final_item = original_data_map[url_key].copy()
                    final_item.update({
                        'city': ai_output.get('city'),
                        'state': ai_output.get('state'),
                        'country': ai_output.get('country')
                    })
                    f_out.write(json.dumps(final_item) + "\n")
                    success_count += 1

            print(f"✅ Successfully merged {success_count}/{len(enriched_batch)} items.")

        except Exception as e:
            print(f"❌ Unexpected Error during parsing/merging: {e}")
            # We do not re-raise; allows the script to try the next batch.

    def run(self, input_file, output_file):
        system_instructions = (
            "You are a data enrichment assistant for VeevaSearch. "
            "You will receive JSON objects with 'text' and 'extra_context_for_ai'.\n\n"
            "TASKS:\n"
            "1. ONLY output posts about pet adoption/rescue.\n"
            "2. Infer 'city', 'state', and 'country'. Use 'extra_context_for_ai' as your primary clue if the 'text' is vague.\n"
            "3. If context mentions 'ACC', 'NYCACC', or 'Brooklyn/Manhattan/Bronx Care Centers', location is New York City, NY, USA.\n"
            "4. If context mentions 'Town of Hempstead', location is Wantagh, NY, USA.\n"
            "5. Use phone area codes (e.g., 516 -> NY) to resolve ambiguous locations.\n"
            "6. Return ONLY valid JSONL. No markdown."
        )

        with open(input_file, "r", encoding="utf-8") as f_in, \
                open(output_file, "w", encoding="utf-8") as f_out:

            batch = []
            for line in f_in:
                if line.strip(): batch.append(line.strip())
                if len(batch) >= 10:
                    self.process_batch(batch, system_instructions, f_out)
                    batch = []
            if batch:
                self.process_batch(batch, system_instructions, f_out)


if __name__ == "__main__":

    enricher = AdoptionDataEnricher(
        api_key=os.getenv("GEMINI_API_KEY"),
        bsky_handle="ethicalsearch.bsky.social",
        bsky_password=os.getenv("BLUESKY_APP_PASSWORD")
    )
    # GEMINI_API_KEY=AIzaSyDUVScEv1IRiTmXiKoLl7eNY4Pj3twL648
    enricher.run(
        "%s04-02-2026/bluesky_rescue_posts_output-w-post-date.jsonl" % NEEDS_HELP_,
        "%s04-02-2026/bluesky_rescue_posts_output-w-loc.jsonl" % NEEDS_HELP_
    )