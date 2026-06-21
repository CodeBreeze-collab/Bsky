import json
import re
import os
import time
from google import genai

# Configuration
NEEDS_HELP_ = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/needs_help/"


class AnimalLocationEnricher:
    def __init__(self, api_key):
        self.client = genai.Client(api_key=api_key)

    def clean_llm_output(self, text):
        text = text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)
        return text

    def process_batch(self, batch_lines, system_instructions, f_out):
        enriched_batch = []
        original_data_map = {}

        for line in batch_lines:
            try:
                item = json.loads(line)
                aid = item.get('animal_id')
                if not aid: continue

                original_data_map[aid] = item

                combined_text = f"Summary: {item.get('final_description', '')}"
                for post in item.get('associated_posts', []):
                    combined_text += f" | Post: {post.get('text', '')}"

                enriched_batch.append({
                    "animal_id": aid,
                    "text": combined_text[:1500]
                })
            except json.JSONDecodeError:
                continue

        if not enriched_batch: return

        try:
            print(f"--- Inferring locations for {len(enriched_batch)} animals ---")
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                config={
                    "system_instruction": system_instructions,
                    "response_mime_type": "application/json",
                },
                contents=json.dumps(enriched_batch),
            )

            cleaned = self.clean_llm_output(response.text)
            ai_results = json.loads(cleaned)
            location_map = {res['animal_id']: res for res in ai_results if 'animal_id' in res}

        except Exception as e:
            print(f"❌ Gemini API Request failed: {e}")
            location_map = {}

        # --- UPDATED MERGE LOGIC ---
        for aid, original_item in original_data_map.items():
            final_item = original_item.copy()

            # 1. Bubble up metadata from associated_posts for the API
            posts = final_item.get('associated_posts', [])
            if posts:
                # Use the last post in the list as the 'most recent' reference
                recent_post = posts[-1]

                # Extract handle from post_url if author_handle isn't explicitly there
                url_parts = recent_post.get('post_url', '').split('/')
                handle = url_parts[4] if len(url_parts) > 4 else "unknown.bsky.social"

                final_item['author_handle'] = handle
                # Map 'posted_at' to 'indexedAt' so the API sorting logic works
                final_item['indexedAt'] = recent_post.get('posted_at', '')
                final_item['post_url'] = recent_post.get('post_url', '')

            # 2. Add Location Data from AI
            if aid in location_map:
                res = location_map[aid]
                final_item['city'] = res.get('city', '')
                final_item['state'] = res.get('state', '')
                final_item['country'] = res.get('country', 'USA')
            else:
                final_item.setdefault('city', '')
                final_item.setdefault('state', '')
                final_item.setdefault('country', 'USA')

            f_out.write(json.dumps(final_item) + "\n")

    def run(self, input_file, output_file):
        system_instructions = (
            "You are a specialized geography assistant for animal rescues. "
            "Identify 'city', 'state' (2-letter code for US/CA), and 'country'.\n"
            "If no location is found, return empty strings for city and state."
        )

        if not os.path.exists(input_file):
            print(f"❌ Input file not found: {input_file}")
            return

        with open(input_file, "r", encoding="utf-8") as f_in, \
                open(output_file, "w", encoding="utf-8") as f_out:

            batch = []
            for line in f_in:
                if line.strip():
                    batch.append(line.strip())
                if len(batch) >= 10:
                    self.process_batch(batch, system_instructions, f_out)
                    batch = []

            if batch:
                self.process_batch(batch, system_instructions, f_out)

        print(f"✅ Finished! API-compatible file saved to: {output_file}")


if __name__ == "__main__":
    api_key = os.getenv("GEMINI_API_KEY")
    enricher = AnimalLocationEnricher(api_key=api_key)

    date_folder = "04-03-2026"
    input_path = f"{NEEDS_HELP_}{date_folder}/animal_centric_posts.jsonl"
    output_path = f"{NEEDS_HELP_}{date_folder}/animal_centric_posts_w-loc-final-2.jsonl"

    enricher.run(input_path, output_path)