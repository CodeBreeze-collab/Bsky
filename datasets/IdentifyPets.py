import json
import os
from datetime import datetime
from google import genai


class RescueLineFinder:
    def __init__(self, api_key, batch_size=25):
        self.client = genai.Client(api_key=api_key)
        self.batch_size = batch_size

    def _log(self, msg):
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

    def _load_jsonl(self, file_path):
        """Load JSONL and preserve line numbers."""
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
            yield data[i:i + self.batch_size]

    def _build_prompt(self, batch):
        formatted = "\n".join(
            [f"{item['line']}: {item['text']}" for item in batch]
        )

        return f"""
You are a strict text classifier.

Task:
Identify which lines contain animal rescue / adoption / foster / shelter transfer / "reserved by rescue" language.

Examples of matches:
- "reserved for rescue"
- "adopted by Pit Bull Rescue of New Jersey"
- "going to rescue"
- "foster picked up"
- "pulled by rescue organization"

DO NOT include:
- general pet posts
- names only
- unrelated updates

Return ONLY a JSON array of line numbers.

Input:
{formatted}
""".strip()

    def _call_gemini(self, prompt):
        response = self.client.models.generate_content(
            model="gemini-2.5-flash",
            config={
                "response_mime_type": "application/json",
            },
            contents=prompt
        )
        return response.text

    def run(self, input_file):
        self._log(f"🚀 Loading file: {input_file}")
        rows = self._load_jsonl(input_file)

        self._log(f"📄 Loaded {len(rows)} rows")

        matches = []

        batch_num = 0
        for batch in self._chunk(rows):
            batch_num += 1
            self._log(f"🤖 Processing batch {batch_num} ({len(batch)} items)")

            prompt = self._build_prompt(batch)

            try:
                raw = self._call_gemini(prompt)
                result = json.loads(raw)

                if isinstance(result, list):
                    matches.extend(result)

            except Exception as e:
                self._log(f"⚠️ Batch {batch_num} failed: {e}")
                self._log(f"Raw response: {raw}")

        self._log(f"✅ Done. Found {len(matches)} matching lines.")

        return sorted(set(matches))


if __name__ == "__main__":
    api_key = os.getenv("GEMINI_API_KEY")

    finder = RescueLineFinder(
        api_key=api_key,
        batch_size=20
    )

    input_path = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/needs_help/05-12-2026/bluesky_rescue_posts_output-w-post-date.jsonl"

    results = finder.run(input_path)

    print("\n🎯 Matching line numbers:")
    print(results)