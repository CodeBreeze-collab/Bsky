import json
import os
import time  # <-- Added missing import for time.sleep
import argparse
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field
from google import genai
from google.genai import types


# =====================================================================
# Schema Definition (Kept lean to save token space during inference)
# =====================================================================
class PostDetail(BaseModel):
    scanned_via: Optional[str] = None
    author_handle: Optional[str] = None
    post_url: Optional[str] = None
    category: Optional[str] = None
    text: str
    image_urls: List[str] = Field(default_factory=list)
    posted_at: Optional[str] = None
    indexedAt: Optional[str] = None


class AnimalRescueProfile(BaseModel):
    animal_id: str = Field(description="Unique identifier like Eggsy_251376 or UnnamedDog_from_Post2")
    name: str = Field(description="The animal's name or 'Unnamed Dog/Cat'")
    species: str = Field(description="Dog, Cat, etc.")
    primary_location: str = Field(description="Shelter or location name, e.g., NYCACC")
    source_urls: List[str] = Field(description="List of unique post URLs relating to this animal")
    status: str = Field(description="Current urgent status, e.g., Needs Rescue, Killed, Reserved")
    final_description: str = Field(description="Comprehensive summary of the animal's situation")
    status_rationale: str = Field(description="Why this status was given based on text evidence")
    conflict_detected: bool = Field(description="True if different posts contain conflicting status info")
    matching_input_indices: List[int] = Field(
        description="The 0-based index/indices of the input posts that belong to this animal.")


class AggregatedRescueReport(BaseModel):
    animals: List[AnimalRescueProfile]


# =====================================================================
# Processing Class
# =====================================================================
class RescueDataAggregator:
    def __init__(self, api_key, batch_size=15):
        # Enforce the 30-second network safety timeout threshold
        http_options = types.HttpOptions(timeout=60000)

        self.client = genai.Client(
            api_key=api_key,
            http_options=http_options
        )
        self.batch_size = batch_size
        self.model_id = "gemini-2.5-flash"  # <-- Defined missing model identifier

    def _log(self, msg):
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

    def _load_jsonl(self, file_path):
        rows = []
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
        return rows

    def _chunk(self, data):
        for i in range(0, len(data), self.batch_size):
            yield data[i:i + self.batch_size]

    def _build_prompt(self, batch):
        simplified_batch = []
        for idx, item in enumerate(batch):
            simplified_batch.append({
                "index": idx,
                "text": item.get("text", ""),
                "url": item.get("post_url", "")
            })

        formatted_posts = json.dumps(simplified_batch, indent=2)

        return f"""
You are an expert animal rescue data aggregator. Your job is to parse raw social media posts and organize them into structured profiles tracking individual animals.

Instructions:
1. Group all posts talking about the exact same animal into a single profile.
2. Read the text across all posts to compile a comprehensive `final_description` and determine their urgent `status`.
3. In `matching_input_indices`, list the integer indices of the posts that belong to this animal.

Raw Input Posts:
{formatted_posts}
""".strip()

    def _call_gemini(self, prompt: str) -> str:
        """
        Fixed method signature, internal naming convention, and enabled
        Structured Output enforcement using your AggregatedRescueReport schema.
        """
        max_retries = 5
        base_delay = 5

        for attempt in range(max_retries):
            try:
                if attempt == 0:
                    time.sleep(1.0)

                # Requesting structured JSON matching the Pydantic schema
                response = self.client.models.generate_content(
                    model=self.model_id,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=AggregatedRescueReport,
                    ),
                )

                if not response.text:
                    finish_reason = "UNKNOWN"
                    if response.candidates:
                        finish_reason = response.candidates[0].finish_reason

                    self._log(f" [!] Gemini returned empty text. Reason: {finish_reason}. Returning empty schema.")
                    return json.dumps({"animals": []})

                return response.text.strip()

            except Exception as e:
                err_msg = str(e).upper()
                retry_keywords = ["429", "RESOURCE_EXHAUSTED", "503", "500", "DISCONNECTED", "RESPONSE", "RESET",
                                  "TIMEOUT", "DEADLINE"]

                if any(x in err_msg for x in retry_keywords):
                    wait_time = base_delay * (2 ** attempt)
                    self._log(
                        f" [!] Gemini Timeout/Server Error ({e}). Retrying in {wait_time}s... (Attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                    continue
                self._log(f"FATAL: Gemini API Call failed: {e}")
                raise e

        raise Exception("Gemini API failed after maximum retries.")

    def run(self, input_file, output_file):
        self._log(f"🚀 Loading file: {input_file}")
        rows = self._load_jsonl(input_file)
        self._log(f"📄 Loaded {len(rows)} raw posts.")

        master_profiles = {}
        batch_num = 0
        for batch in self._chunk(rows):
            batch_num += 1
            self._log(f"🤖 Processing batch {batch_num} ({len(batch)} items)...")

            prompt = self._build_prompt(batch)
            raw_json = ""

            try:
                raw_json = self._call_gemini(prompt)
                batch_data = json.loads(raw_json)

                for animal in batch_data.get("animals", []):
                    original_posts = []
                    for idx in animal.get("matching_input_indices", []):
                        if 0 <= idx < len(batch):
                            original_posts.append(batch[idx])

                    a_id = animal["animal_id"]
                    if a_id in master_profiles:
                        master_profiles[a_id]["source_urls"] = list(
                            set(master_profiles[a_id]["source_urls"] + animal["source_urls"]))

                        existing_urls = {p.get("post_url") for p in master_profiles[a_id]["post_details"]}
                        for post in original_posts:
                            if post.get("post_url") not in existing_urls:
                                master_profiles[a_id]["post_details"].append(post)

                        master_profiles[a_id]["status"] = animal["status"]
                        master_profiles[a_id]["final_description"] = animal["final_description"]
                    else:
                        master_profiles[a_id] = {
                            "animal_id": animal["animal_id"],
                            "name": animal["name"],
                            "species": animal["species"],
                            "primary_location": animal["primary_location"],
                            "source_urls": animal["source_urls"],
                            "status": animal["status"],
                            "final_description": animal["final_description"],
                            "status_rationale": animal["status_rationale"],
                            "conflict_detected": animal["conflict_detected"],
                            "post_details": original_posts
                        }

                self._log(f"📶 Batch {batch_num} processed successfully.")

            except Exception as e:
                self._log(f"⚠️ Batch {batch_num} failed: {e}")
                if raw_json:
                    self._log(f"🔍 DEBUG: Trailing response content:\n... {raw_json[-300:]}")
                else:
                    self._log("🔍 DEBUG: No response was returned from the model.")

        final_list = list(master_profiles.values())

        self._log(f"💾 Saving {len(final_list)} structured animal profiles to {output_file}")
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(final_list, f, indent=2, ensure_ascii=False)

        self._log("✅ Done!")
        return final_list


if __name__ == "__main__":
    default_input = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/needs_help/06-08-2026/bluesky_rescue_posts_output-w-post-date.jsonl"
    default_output = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/needs_help/06-08-2026/aggregated_rescue_profiles.json"

    parser = argparse.ArgumentParser(description="Identify and Aggregate Rescue Pets Engine")
    parser.add_argument("--input-file", type=str, default=default_input, help="Path to input raw posts JSONL file")
    parser.add_argument("--output-file", type=str, default=default_output, help="Path to output profiles JSON file")
    parser.add_argument("--batch-size", type=int, default=15, help="Batch processing size for Gemini context mapping")

    args = parser.parse_args()

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("[!] Error: GEMINI_API_KEY environment variable is missing.")
    else:
        aggregator = RescueDataAggregator(
            api_key=api_key,
            batch_size=args.batch_size
        )
        results = aggregator.run(args.input_file, args.output_file)