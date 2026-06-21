import json
import os
import time
from datetime import datetime
from google import genai


class RobustRescueCleaner:
    def __init__(self, api_key, input_file="/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/ig_detected_rescues.jsonl",
                 checkpoint_file="IG_rescues.txt",
                 output_file="final_clean_rescues.txt",
                 batch_size=30):
        self.client = genai.Client(api_key=api_key)
        self.input_file = input_file
        self.checkpoint_file = checkpoint_file
        self.output_file = output_file
        self.batch_size = batch_size

    def _log(self, msg):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

    def get_remaining_names(self):
        """Reads input and excludes names already found in the checkpoint file."""
        raw_names = set()
        if os.path.exists(self.input_file):
            with open(self.input_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            name = json.loads(line).get("rescue_name")
                            if name: raw_names.add(name)
                        except:
                            continue

        processed_names = set()
        if os.path.exists(self.checkpoint_file):
            with open(self.checkpoint_file, "r", encoding="utf-8") as f:
                processed_names = {line.strip() for line in f if line.strip()}

        remaining = list(raw_names - processed_names)
        self._log(f"📊 Total raw unique names: {len(raw_names)}")
        self._log(f"⏭️ Already processed: {len(processed_names)}")
        self._log(f"🚀 Remaining to process: {len(remaining)}")
        return remaining

    def _build_prompt(self, names):
        names_list = "\n".join([f"- {name}" for name in names])
        return f"""
Normalize these animal rescue names. 
Rules:
1. Fix typos and capitalization.
2. Expand acronyms if obvious (e.g., "nycacc" -> "Animal Care Centers of NYC").
3. Merge duplicates.
4. Return a JSON array of strings: ["Name 1", "Name 2"]

Names to process:
{names_list}
""".strip()

    def run(self):
        todo = self.get_remaining_names()
        if not todo:
            self._log("✅ All names already processed.")
            return

        for i in range(0, len(todo), self.batch_size):
            batch = todo[i: i + self.batch_size]
            self._log(f"🤖 Cleaning batch {i // self.batch_size + 1} ({len(batch)} names)...")

            try:
                response = self.client.models.generate_content(
                    model="gemini-2.5-flash",
                    config={"response_mime_type": "application/json"},
                    contents=self._build_prompt(batch)
                )

                clean_batch = json.loads(response.text)

                # 1. Append clean names to final output
                with open(self.output_file, "a", encoding="utf-8") as f:
                    for name in clean_batch:
                        f.write(f"{name}\n")

                # 2. Update checkpoint so we don't process these raw names again
                with open(self.checkpoint_file, "a", encoding="utf-8") as f:
                    for raw_name in batch:
                        f.write(f"{raw_name}\n")

                self._log(f"✅ Batch complete. Progress saved.")

                # Brief sleep to respect rate limits
                time.sleep(1)

            except Exception as e:
                self._log(f"⚠️ Crash/Error on batch: {e}")
                self._log("Safe to restart script; checkpoint saved progress.")
                break


if __name__ == "__main__":
    api_key = os.getenv("GEMINI_API_KEY")
    cleaner = RobustRescueCleaner(api_key=api_key, batch_size=25)
    cleaner.run()