import os
import json
import time
import threading
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from serpapi import GoogleSearch
from concurrent.futures import ThreadPoolExecutor, as_completed
from google import genai
from google.genai import types


class RescueScraper:
    def __init__(self):
        # --- CONFIG ---
        self.SERPAPI_KEY = os.environ.get("SERPAPI_KEY")
        self.GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

        self.MODEL_ID = "gemini-2.5-flash"

        self.OUTPUT_FILE = "rescues.jsonl"
        self.SEEN_FILE = "seen_keys.json"
        self.PROCESSED_DOMAINS_FILE = "processed_domains.json"
        self.CHECKPOINT_FILE = "checkpoint.json"

        self.MAX_WORKERS = 8

        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0"})

        self.client = genai.Client(api_key=self.GEMINI_API_KEY)

        self.lock = threading.Lock()

        # --- STATE ---
        self.seen_keys = self.load_set(self.SEEN_FILE)
        self.processed_domains = self.load_set(self.PROCESSED_DOMAINS_FILE)
        self.checkpoint = self.load_checkpoint()

        print(f"[INIT] Seen: {len(self.seen_keys)}")
        print(f"[INIT] Domains: {len(self.processed_domains)}")

    # ------------------------
    # STATE MANAGEMENT
    # ------------------------

    def load_set(self, path):
        if not os.path.exists(path):
            return set()
        try:
            return set(json.load(open(path)))
        except:
            return set()

    def save_set(self, path, data):
        with open(path, "w") as f:
            json.dump(list(data), f)

    def load_checkpoint(self):
        if not os.path.exists(self.CHECKPOINT_FILE):
            return {}
        try:
            return json.load(open(self.CHECKPOINT_FILE))
        except:
            return {}

    def save_checkpoint(self):
        with open(self.CHECKPOINT_FILE, "w") as f:
            json.dump(self.checkpoint, f)

    # ------------------------
    # UTILITIES
    # ------------------------

    def normalize_domain(self, url):
        try:
            return urlparse(url).netloc.replace("www.", "")
        except:
            return ""

    def is_valid_candidate(self, url):
        bad = ["facebook", "instagram", "yelp", "twitter"]
        return not any(b in url.lower() for b in bad)

    # ------------------------
    # GOOGLE SEARCH
    # ------------------------

    def get_google_links(self, query):
        links = []

        for start in range(0, 40, 10):
            try:
                search = GoogleSearch({
                    "q": query,
                    "api_key": self.SERPAPI_KEY,
                    "start": start
                })

                results = search.get_dict()

                for r in results.get("organic_results", []):
                    if r.get("link"):
                        links.append(r["link"])

                time.sleep(1)

            except Exception as e:
                print(f"[SERP ERROR] {e}")

        return list(set(links))

    # ------------------------
    # LINK EXTRACTION
    # ------------------------

    def extract_links(self, url):
        try:
            res = self.session.get(url, timeout=15)
            soup = BeautifulSoup(res.text, "html.parser")

            links = set()

            for a in soup.find_all("a", href=True):
                href = urljoin(url, a["href"])

                if href.startswith("http") and self.is_valid_candidate(href):
                    links.add(href)

            return list(links)

        except:
            return []

    def is_likely_rescue(self, url):
        keywords = ["rescue", "shelter", "animal", "pet", "humane"]
        u = url.lower()
        return any(k in u for k in keywords)

    # ------------------------
    # GEMINI ENRICHMENT
    # ------------------------

    def enrich(self, url):
        try:
            res = self.session.get(url, timeout=10)
            text = BeautifulSoup(res.text, "html.parser").get_text(" ", strip=True)[:15000]

            prompt = f"""
            Extract organization info.

            Return JSON:
            {{
                "name": "",
                "city": "",
                "state": "",
                "email": "",
                "phone": ""
            }}

            Content:
            {text}
            """

            response = self.client.models.generate_content(
                model=self.MODEL_ID,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )

            data = json.loads(response.text)
            data["website"] = url

            return data

        except:
            return None

    # ------------------------
    # WRITING (REAL-TIME SAFE)
    # ------------------------

    def write_result(self, entry, file_handle):
        key = (entry.get("name", "") + entry.get("city", "")).lower().strip()

        if not key:
            return False

        with self.lock:
            if key in self.seen_keys:
                return False

            file_handle.write(json.dumps(entry) + "\n")
            file_handle.flush()

            self.seen_keys.add(key)

            if len(self.seen_keys) % 10 == 0:
                self.save_set(self.SEEN_FILE, self.seen_keys)

            return True

    def mark_domain_done(self, domain):
        with self.lock:
            self.processed_domains.add(domain)

            if len(self.processed_domains) % 20 == 0:
                self.save_set(self.PROCESSED_DOMAINS_FILE, self.processed_domains)

    # ------------------------
    # MAIN PIPELINE
    # ------------------------

    def process_query(self, query, file_handle):
        print(f"\n[+] {query}")

        if self.checkpoint.get("last_query") == query:
            print("[Skipping completed]")
            return

        google_links = self.get_google_links(query)
        print(f"   SERP links: {len(google_links)}")

        candidate_sites = set()

        # expand directories
        for link in google_links:
            sub_links = self.extract_links(link)

            for l in sub_links:
                if self.is_likely_rescue(l):
                    candidate_sites.add(l)

        print(f"   Candidates: {len(candidate_sites)}")

        futures = {}

        with ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as executor:
            for url in candidate_sites:
                domain = self.normalize_domain(url)

                if not domain or domain in self.processed_domains:
                    continue

                futures[executor.submit(self.enrich, url)] = (url, domain)

            for future in as_completed(futures):
                url, domain = futures[future]

                try:
                    result = future.result()

                    if result and result.get("name"):
                        if self.write_result(result, file_handle):
                            print(f"   ✓ {result['name']}")

                    self.mark_domain_done(domain)

                except Exception as e:
                    print(f"   [!] Error: {e}")

        self.checkpoint["last_query"] = query
        self.save_checkpoint()

    # ------------------------
    # RUNNER
    # ------------------------

    def run(self):
        states = ["New York"]

        queries = [
            "animal rescue directory in {state}",
            "list of animal shelters in {state}",
            "dog rescue organizations in {state}",
            "humane society {state} list"
        ]

        with open(self.OUTPUT_FILE, "a") as f:
            for state in states:
                for q in queries:
                    full_query = q.format(state=state)
                    self.process_query(full_query, f)

        print("\n[Done]")


if __name__ == "__main__":
    scraper = RescueScraper()
    scraper.run()