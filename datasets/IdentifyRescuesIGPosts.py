import json
import os
from datetime import datetime
from google import genai


class InstagramRescueFinder:
    def __init__(self, api_key, batch_size=15, output_file="ig_detected_rescues.jsonl"):
        self.client = genai.Client(api_key=api_key)
        self.batch_size = batch_size
        self.output_file = output_file

    def _log(self, msg):
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

    def _load_jsonl(self, file_path):
        rows = []
        with open(file_path, "r", encoding="utf-8") as f:
            for i, line in enumerate(f, start=1):
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                    result_part = obj.get("result", {})
                    rows.append({
                        "line": i,
                        "text": result_part.get("caption", ""),
                        "url": obj.get("instagram_url") or result_part.get("url", ""),
                        "owner": result_part.get("ownerUsername", "unknown")
                    })
                except json.JSONDecodeError:
                    self._log(f"⚠️ Skipping malformed JSON on line {i}")
        return rows

    def _chunk(self, data):
        for i in range(0, len(data), self.batch_size):
            yield (i // self.batch_size + 1, data[i:i + self.batch_size])

    def _build_prompt(self, batch):
        """
        Extracts rescue names.
        Note: We clean newlines outside the f-string to avoid Python errors.
        """
        lines = []
        for item in batch:
            # Avoid backslashes inside f-string braces
            clean_text = item['text'].replace('\n', ' ')
            lines.append(f"{item['line']}: {clean_text}")

        formatted_text = "\n".join(lines)

        return f"""
You are an expert in Animal Rescue data extraction.

Task:
Extract the PROPER NAMES of specific animal rescue organizations, shelters, or sanctuaries mentioned in the Instagram captions.

Rules:
1. Extract the full formal name (e.g., "SNARR Northeast", "Austin Pets Alive").
2. If the text mentions a handle like @snarr_northeast_rescue, include it.
3. Ignore generic terms like "the rescue," "the shelter," or "vet hospital" unless it's part of a proper name.
4. If no specific organization is mentioned, return an empty array [].

Return ONLY a JSON array of objects:
[
  {{"line": 1, "entity": "SNARR Northeast"}}
]

Input Text:
{formatted_text}
""".strip()

    def _call_gemini(self, prompt):
        # Using 1.5-flash or 2.0-flash
        response = self.client.models.generate_content(
            model="gemini-2.5-flash",
            config={"response_mime_type": "application/json"},
            contents=prompt
        )
        return response.text

    def _write_results(self, extractions, batch_lookup):
        try:
            with open(self.output_file, "a", encoding="utf-8") as f:
                for ext in extractions:
                    line_num = ext.get("line")
                    entity = ext.get("entity")
                    original = batch_lookup.get(line_num, {})

                    result_record = {
                        "rescue_name": entity,
                        "ig_url": original.get("url"),
                        "poster_username": original.get("owner"),
                        "line_number": line_num,
                        "detected_at_iso": datetime.utcnow().isoformat()
                    }
                    f.write(json.dumps(result_record, ensure_ascii=False) + "\n")
        except Exception as e:
            self._log(f"⚠️ Write error: {e}")

    def run(self, input_file):
        self._log(f"🚀 Analyzing Instagram Data: {input_file}")
        rows = self._load_jsonl(input_file)
        self._log(f"📄 Loaded {len(rows)} posts")

        with open(self.output_file, "w") as f:
            pass

        total_matches = 0

        for batch_num, batch in self._chunk(rows):
            self._log(f"🤖 Processing batch {batch_num} ({len(batch)} posts)...")
            batch_lookup = {item['line']: item for item in batch}

            # This is the line that was failing:
            prompt = self._build_prompt(batch)

            try:
                raw_json = self._call_gemini(prompt)
                extractions = json.loads(raw_json)

                if extractions:
                    self._write_results(extractions, batch_lookup)
                    total_matches += len(extractions)
                    for e in extractions:
                        self._log(f"✨ Detected: {e['entity']}")
            except Exception as e:
                self._log(f"⚠️ Batch {batch_num} failed: {e}")

        self._log(f"✅ Finished. {total_matches} rescues identified.")


if __name__ == "__main__":
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Please set your GEMINI_API_KEY.")
    else:
        input_path = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/instagram_post_results.jsonl"
        finder = InstagramRescueFinder(api_key=api_key, batch_size=15)
        finder.run(input_path)