import json
import re
import os
import requests
from bs4 import BeautifulSoup
from google import genai
from atproto import Client


class AdoptionDataEnricher:
    def __init__(self, api_key, bsky_handle=None, bsky_password=None):
        # The key is now passed from the environment variable in the main block
        self.client = genai.Client(api_key=api_key)
        self.bsky_client = None

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
            parts = post_url.strip("/").split('/')
            handle = parts[-3]
            post_id = parts[-1]
            profile = self.bsky_client.get_profile(actor=handle)
            uri = f"at://{profile.did}/app.bsky.feed.post/{post_id}"
            thread_res = self.bsky_client.app.bsky.feed.get_post_thread({'uri': uri, 'depth': 0, 'parentHeight': 1})
            thread_view = thread_res.thread
            if hasattr(thread_view, 'parent') and thread_view.parent is not None:
                if hasattr(thread_view.parent, 'post'):
                    return f"[Parent Post Context: {thread_view.parent.post.record.text}]"
            return ""
        except Exception:
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

        for item in batch:
            original_text = item.get('text', '')
            quoted_text = item.get('quoted_text', '')
            combined_text = f"{original_text} {quoted_text}"

            # Extract all URLs for the image_urls field
            urls = list(set(re.findall(r'(https?://\S+)', combined_text)))

            # Gather extra context from the first link
            parent_context = self._get_bsky_parent_context(item.get('post_url', ''))
            link_context = self._get_link_context(urls[0]) if urls else ""

            # Inject context and extracted data for the LLM
            item['extra_context_for_ai'] = f"{parent_context} {link_context}".strip()
            item['all_extracted_urls'] = urls
            enriched_batch.append(item)

        raw_input = "\n".join([json.dumps(i) for i in enriched_batch])

        # Using the specified Gemini model
        response = self.client.models.generate_content(
            model="gemini-2.5-flash",
            config={
                "system_instruction": system_instructions,
                "response_mime_type": "application/json",
            },
            contents=raw_input,
        )

        cleaned = self.clean_llm_output(response.text)

        for line in cleaned.splitlines():
            line = line.strip()
            if not line: continue
            try:
                processed_item = json.loads(line)
                f_out.write(json.dumps(processed_item) + "\n")
            except json.JSONDecodeError:
                continue

    def run(self, input_file, output_file):
        system_instructions = (
            "You are a data enrichment assistant. You will receive JSON with 'handle', 'text', 'quoted_text', 'indexedAt', and 'all_extracted_urls'.\n\n"
            "TASKS:\n"
            "1. ONLY output posts about pet adoption/rescue. Ignore everything else.\n"
            "2. TRANSFORM the schema to the following keys:\n"
            "   - 'author_handle': Use value from 'handle'.\n"
            "   - 'post_url': Keep as is.\n"
            "   - 'text': Combine original 'text' and 'quoted_text' into one clear description.\n"
            "   - 'created_at': Use value from 'indexedAt'.\n"
            "   - 'image_urls': Use the list provided in 'all_extracted_urls'.\n"
            "   - 'city', 'state', 'country': Infer these accurately.\n"
            "3. LOCATION LOGIC: If 'NYCACC' or 'Manhattan/Bronx/Brooklyn' is mentioned, location is New York, NY, USA.\n"
            "4. Return ONLY valid JSONL. No markdown formatting."
        )

        with open(input_file, "r", encoding="utf-8") as f_in, \
                open(output_file, "w", encoding="utf-8") as f_out:

            batch = []
            for line in f_in:
                if not line.strip():
                    continue

                try:
                    data = json.loads(line)
                    # FILTER: Only process lines where category is NEED_A_HOME
                    if data.get("category") == "NEED_A_HOME":
                        batch.append(data)
                except json.JSONDecodeError:
                    continue

                if len(batch) >= 10:
                    self.process_batch(batch, system_instructions, f_out)
                    batch = []

            if batch:
                self.process_batch(batch, system_instructions, f_out)


if __name__ == "__main__":
    # Load API Key from environment variable
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        print("Error: Please set the GEMINI_API_KEY environment variable.")
    else:
        enricher = AdoptionDataEnricher(api_key=api_key)

        # File paths
        input_path = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/needs_help/03-11-2026/bluesky_rescue_posts_output.jsonl"
        output_path = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/needs_help/03-11-2026/bluesky_rescue_posts_w_loc.jsonl"

        enricher.run(input_path, output_path)