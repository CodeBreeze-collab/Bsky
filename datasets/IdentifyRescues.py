import json
import os
from datetime import datetime
from google import genai


class RescueLineFinder:
    def __init__(self, api_key, batch_size=40, output_file="morgfairsdogs_bsky_social_rescues.jsonl"):
        self.client = genai.Client(api_key=api_key)
        self.batch_size = batch_size
        self.output_file = output_file

    def _log(self, msg):
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

    def _load_jsonl(self, file_path):
        rows = []
        with open(file_path, "r", encoding="utf-8") as f:
            for i, line in enumerate(f, start=1):
                if line.strip():
                    obj = json.loads(line)
                    rows.append({
                        "line": i,
                        "text": obj.get("text", ""),
                        "url": obj.get("url", "")
                    })
        return rows

    def _chunk(self, data):
        for i in range(0, len(data), self.batch_size):
            yield (i // self.batch_size + 1, data[i:i + self.batch_size])

    def _build_prompt(self, batch):
        formatted = "\n".join(
            [f"{item['line']}: {item['text']}" for item in batch]
        )

        return f"""
You are a Named Entity Recognizer. 

Task:
Extract the PROPER NAMES of specific animal rescue organizations, sanctuaries, or shelters mentioned in the text.

Rules:
1. ONLY extract the specific name (e.g., "Miracle Lane Farm N Sanctuary", "Austin Pets Alive").
2. DO NOT extract generic words like "shelter", "rescue", "foster", or "adopted".
3. If a handle is used (e.g., @RescueOrg), extract the handle.
4. If no specific organization is named, return an empty array [].

Return ONLY a JSON array of objects:
[
  {{"line": 14, "entity": "Miracle Lane Farm N Sanctuary"}}
]

Input:
{formatted}
""".strip()

    def _call_gemini(self, prompt):
        response = self.client.models.generate_content(
            model="gemini-2.5-flash",
            config={"response_mime_type": "application/json"},
            contents=prompt
        )
        return response.text

    def _write_realtime_results(self, extractions, batch_lookup):
        """
        Writes each match to the JSONL file immediately.
        Each line contains the rescue name and the original post URL.
        """
        try:
            with open(self.output_file, "a", encoding="utf-8") as f:
                for ext in extractions:
                    line_num = ext.get("line")
                    entity = ext.get("entity")

                    # Find the original URL from our batch lookup
                    original_post = batch_lookup.get(line_num, {})

                    result_record = {
                        "rescue_name": entity,
                        "post_url": original_post.get("url"),
                        "post_text": original_post.get("text"),
                        "line_number": line_num,
                        "detected_at": datetime.utcnow().isoformat()
                    }

                    f.write(json.dumps(result_record, ensure_ascii=False) + "\n")

                f.flush()
                os.fsync(f.fileno())
        except Exception as e:
            self._log(f"⚠️ Write error: {e}")

    def run(self, input_file):
        self._log(f"🚀 Loading file: {input_file}")
        rows = self._load_jsonl(input_file)
        self._log(f"📄 Loaded {len(rows)} rows")

        # Clear output file for fresh run
        with open(self.output_file, "w") as f:
            pass

        total_matches = 0

        for batch_num, batch in self._chunk(rows):
            self._log(f"🤖 Processing batch {batch_num}...")

            # Create a quick lookup for this batch to grab URLs later
            batch_lookup = {item['line']: item for item in batch}

            prompt = self._build_prompt(batch)

            try:
                raw = self._call_gemini(prompt)
                extractions = json.loads(raw)

                if extractions:
                    self._write_realtime_results(extractions, batch_lookup)
                    total_matches += len(extractions)
                    for e in extractions:
                        self._log(f"✨ Found: {e['entity']}")

            except Exception as e:
                self._log(f"⚠️ Batch {batch_num} failed: {e}")

        self._log(f"✅ Done. {total_matches} total matches saved to {self.output_file}")


if __name__ == "__main__":
    api_key = os.getenv("GEMINI_API_KEY")
    finder = RescueLineFinder(api_key=api_key, batch_size=40)

    input_path = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/morgfairsdogs_bsky_social_rescues.jsonl"
    finder.run(input_path)