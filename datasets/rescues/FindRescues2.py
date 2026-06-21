import os
import json
import time
import sys
import threading
import requests
from serpapi import GoogleSearch
from google import genai
from google.genai import types
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONFIG ---
SERPAPI_KEY = os.environ.get("SERPAPI_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

MODEL_ID = "gemini-2.5-flash"

OUTPUT_FILE = "rescues_results-v3-p2.jsonl"
URL_CACHE_FILE = "visited_urls.json"
CHECKPOINT_FILE = "checkpoint.json"

MAX_PAGES = 4
START_PAGE = 2
MAX_WORKERS = 5   # 👈 concurrency level

EXCLUDED_DOMAINS = [
    "yelp.com",
    "facebook.com",
    "instagram.com",
    "bringfido.com"
]

if not SERPAPI_KEY or not GEMINI_API_KEY:
    print("[!] Missing API keys")
    sys.exit(1)

client = genai.Client(api_key=GEMINI_API_KEY)

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0"})

lock = threading.Lock()

# --- LOAD STATE ---
def load_json_set(file):
    if not os.path.exists(file):
        return set()
    try:
        with open(file, "r") as f:
            return set(json.load(f))
    except:
        return set()

def save_json_set(file, data):
    with open(file, "w") as f:
        json.dump(list(data), f)

def load_seen_entries():
    seen = set()
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "r") as f:
            for line in f:
                try:
                    e = json.loads(line)
                    key = (
                        (e.get("name") or "") +
                        (e.get("city") or "") +
                        (e.get("state") or "")
                    ).lower().strip()
                    if key:
                        seen.add(key)
                except:
                    continue
    return seen

def load_checkpoint():
    if not os.path.exists(CHECKPOINT_FILE):
        return {}
    try:
        with open(CHECKPOINT_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_checkpoint(state):
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(state, f)


# --- HELPERS ---
def is_valid_link(url):
    if not url:
        return False
    url = url.lower()
    return not any(d in url for d in EXCLUDED_DOMAINS)


def get_paginated_links(query):
    links = []

    for start in range((START_PAGE - 1) * 10,
                       (START_PAGE - 1 + MAX_PAGES) * 10,
                       10):

        print(f"   🔎 SERP start={start}")

        try:
            search = GoogleSearch({
                "q": query,
                "api_key": SERPAPI_KEY,
                "start": start
            })

            results = search.get_dict()
            organic = results.get("organic_results", [])

            for r in organic:
                link = r.get("link")
                if is_valid_link(link):
                    links.append(link)

            time.sleep(1)

        except Exception as e:
            print(f"   [!] SERP error: {e}")

    return list(set(links))


def deep_scan_homepage(name, url):
    try:
        res = session.get(url, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")

        emails = [
            m['href'].replace('mailto:', '').split('?')[0]
            for m in soup.select('a[href^=mailto]')
        ]

        text = soup.get_text(" ", strip=True)[:10000]

        prompt = f"""
        Extract email and phone for {name}.
        Return JSON: {{ "email": "", "phone": "" }}
        Emails found: {emails}
        {text}
        """

        response = client.models.generate_content(
            model=MODEL_ID,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )

        return json.loads(response.text)

    except:
        return None


def scrape_url(url, seen, visited):
    if url in visited:
        return []

    try:
        res = session.get(url, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")

        clean_html = str(soup)[:25000]

        prompt = f"""
        Extract animal rescues as JSON list:
        name, city, state, website, email, phone.
        {clean_html}
        """

        response = client.models.generate_content(
            model=MODEL_ID,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )

        data = json.loads(response.text)

        results = []

        for entry in data:
            try:
                key = (
                    (entry.get("name") or "") +
                    (entry.get("city") or "") +
                    (entry.get("state") or "")
                ).lower().strip()

                if not key or key in seen:
                    continue

                if entry.get("website") and (
                    not entry.get("email") or not entry.get("phone")
                ):
                    details = deep_scan_homepage(entry["name"], entry["website"])
                    if details:
                        entry["email"] = details.get("email") or ""
                        entry["phone"] = details.get("phone") or ""

                results.append(entry)

            except:
                continue

        with lock:
            visited.add(url)

        return results

    except Exception as e:
        print(f"      [!] Scrape fail: {url} | {e}")
        return []


# --- MAIN ---
if __name__ == "__main__":
    states = ["New Jersey", "Northern Virginia", "Connecticut", "Maryland"]

    queries = [
        "animal rescue list",
        "dog rescue organizations",
        "animal shelter directory",
        "no kill shelters",
        "animal rescue nonprofit"
    ]

    seen = load_seen_entries()
    visited_urls = load_json_set(URL_CACHE_FILE)
    checkpoint = load_checkpoint()

    print(f"[!] Loaded {len(seen)} seen entries")
    print(f"[!] Loaded {len(visited_urls)} visited URLs")

    with open(OUTPUT_FILE, "a") as f:

        for state in states:
            for q in queries:
                query = f"{q} in {state}"

                if checkpoint.get("last_query") == query:
                    print(f"[Resume] Continuing {query}")

                print(f"\n[+] {query}")

                links = get_paginated_links(query)

                with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                    futures = [
                        executor.submit(scrape_url, link, seen, visited_urls)
                        for link in links
                    ]

                    for future in as_completed(futures):
                        try:
                            results = future.result()

                            for entry in results:
                                key = (
                                    (entry.get("name") or "") +
                                    (entry.get("city") or "") +
                                    (entry.get("state") or "")
                                ).lower().strip()

                                if key and key not in seen:
                                    with lock:
                                        f.write(json.dumps(entry) + "\n")
                                        f.flush()
                                        seen.add(key)

                                        print(f"   ✓ {entry.get('name')}")

                        except Exception as e:
                            print(f"   [!] Future error: {e}")

                checkpoint["last_query"] = query
                save_checkpoint(checkpoint)
                save_json_set(URL_CACHE_FILE, visited_urls)

    print(f"\n[Done] Total: {len(seen)} rescues")