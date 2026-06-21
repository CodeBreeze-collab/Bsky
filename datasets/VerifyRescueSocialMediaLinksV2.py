import os
import json
import requests
import threading
from queue import Queue
from bs4 import BeautifulSoup
from google import genai


INPUT_DIR = "/Users/hdon/Desktop/Apify-Actor-Rescues/"
OUTPUT_FILE = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/rescues/verified_rescues_v2.json"

BATCH_SIZE = 20
WORKERS = 4


class RescueValidator:

    def __init__(self, api_key):
        self.client = genai.Client(api_key=api_key)
        self.processed_urls = set()
        self.lock = threading.Lock()

    # ------------------------------
    # Restart safety
    # ------------------------------
    def load_processed(self):

        if not os.path.exists(OUTPUT_FILE):
            return

        with open(OUTPUT_FILE, "r") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    self.processed_urls.add(obj["socialProfileUrl"])
                except:
                    continue

        print(f"Loaded {len(self.processed_urls)} processed URLs")

    # ------------------------------
    # Gather and dedupe URLs
    # ------------------------------
    def collect_unique_profiles(self):

        urls = {}

        for file in os.listdir(INPUT_DIR):

            if not file.endswith(".json"):
                continue

            path = os.path.join(INPUT_DIR, file)

            try:
                data = json.load(open(path))

                for item in data:

                    url = item.get("socialProfileUrl")

                    if not url:
                        continue

                    if url in self.processed_urls:
                        continue

                    urls[url] = {
                        "inputProfileName": item.get("inputProfileName"),
                        "social": item.get("social"),
                        "socialProfileUrl": url
                    }

            except Exception as e:
                print("skip", file, e)

        print("Unique URLs:", len(urls))

        return list(urls.values())

    # ------------------------------
    # Scrape profile context
    # ------------------------------
    def scrape_context(self, url):

        try:

            headers = {
                "User-Agent": "Mozilla/5.0"
            }

            r = requests.get(url, headers=headers, timeout=6)

            soup = BeautifulSoup(r.text, "html.parser")

            title = soup.title.string if soup.title else ""

            desc = ""
            m = soup.find("meta", {"name": "description"})
            if m:
                desc = m.get("content", "")

            og = soup.find("meta", {"property": "og:description"})
            if og:
                desc = og.get("content", desc)

            return f"{title} {desc}"[:500]

        except:
            return ""

    # ------------------------------
    # Gemini call
    # ------------------------------
    def validate_batch(self, batch):

        system_instruction = (
            "You validate whether social media profiles belong to animal rescues.\n\n"
            "Input fields:\n"
            "inputProfileName\n"
            "social\n"
            "socialProfileUrl\n"
            "pageContext\n\n"
            "Determine if the profile belongs to an ANIMAL RESCUE.\n\n"
            "If valid rescue, infer:\n"
            "city\n"
            "state_or_region\n"
            "country\n\n"
            "Return JSON objects with:\n"
            "inputProfileName\n"
            "social\n"
            "socialProfileUrl\n"
            "is_valid_rescue_profile\n"
            "confidence\n"
            "city\n"
            "state_or_region\n"
            "country\n"
            "reason\n\n"
            "Return JSON only."
        )

        raw_input = "\n".join(json.dumps(i) for i in batch)

        try:

            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                config={
                    "system_instruction": system_instruction,
                    "response_mime_type": "application/json",
                },
                contents=raw_input,
            )

            text = response.text.strip()

            if text.startswith("```"):
                text = "\n".join(
                    l for l in text.splitlines()
                    if not l.startswith("```")
                )

            return json.loads(text)

        except Exception as e:

            print("Gemini error:", e)

            return []

    # ------------------------------
    # Worker
    # ------------------------------
    def worker(self, queue, f_out):

        while True:

            batch = queue.get()

            if batch is None:
                break

            results = self.validate_batch(batch)

            with self.lock:

                for r in results:

                    url = r.get("socialProfileUrl")

                    if url in self.processed_urls:
                        continue

                    self.processed_urls.add(url)

                    f_out.write(json.dumps(r) + "\n")
                    f_out.flush()

            queue.task_done()

    # ------------------------------
    # Run pipeline
    # ------------------------------
    def run(self):

        self.load_processed()

        profiles = self.collect_unique_profiles()

        queue = Queue()

        with open(OUTPUT_FILE, "a") as f_out:

            threads = []

            for _ in range(WORKERS):

                t = threading.Thread(
                    target=self.worker,
                    args=(queue, f_out)
                )

                t.start()
                threads.append(t)

            batch = []

            for item in profiles:

                context = self.scrape_context(item["socialProfileUrl"])

                item["pageContext"] = context

                batch.append(item)

                if len(batch) >= BATCH_SIZE:

                    queue.put(batch)
                    batch = []

            if batch:
                queue.put(batch)

            queue.join()

            for _ in threads:
                queue.put(None)

            for t in threads:
                t.join()


if __name__ == "__main__":

    validator = RescueValidator(
        api_key=os.getenv("GEMINI_API_KEY")
    )

    validator.run()