import os
import json
import time
import sys
import requests
from serpapi import GoogleSearch
from google import genai
from google.genai import types
from bs4 import BeautifulSoup

# --- CONFIGURATION ---
SERPAPI_KEY = os.environ.get("SERPAPI_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
MODEL_ID = "gemini-2.5-flash"
OUTPUT_FILE = "rescues_results-rt.jsonl"

if not SERPAPI_KEY or not GEMINI_API_KEY:
    print("[!] ERROR: Missing SERPAPI_KEY or GEMINI_API_KEY in environment.")
    sys.exit(1)

client = genai.Client(api_key=GEMINI_API_KEY)

# Safety settings
safety_settings = [
    types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
    types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
    types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
    types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
]

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
})


def deep_scan_homepage(rescue_name, homepage_url):
    excluded_domains = ["google.com", "bringfido.com", "yelp.com", "facebook.com", "instagram.com"]
    if not homepage_url or any(domain in homepage_url.lower() for domain in excluded_domains):
        return None

    try:
        res = session.get(homepage_url, timeout=12)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')
        emails = [m['href'].replace('mailto:', '').split('?')[0] for m in soup.select('a[href^=mailto]')]

        for s in soup(["script", "style", "nav", "footer", "header"]):
            s.extract()
        body_text = soup.get_text(separator=' ', strip=True)[:12000]

        prompt = (
            f"Identify the official contact email and phone number for '{rescue_name}' from the text below. "
            "Return ONLY a JSON object with keys 'email' and 'phone'. "
            f"Contextual Emails: {', '.join(set(emails))}\n\nWebpage Text:\n{body_text}"
        )

        response = client.models.generate_content(
            model=MODEL_ID,
            contents=prompt,
            config=types.GenerateContentConfig(safety_settings=safety_settings, response_mime_type="application/json")
        )
        return json.loads(response.text.strip())
    except Exception:
        return None


def scrape_and_parse(url):
    if url.lower().endswith(".pdf"): return []
    try:
        print(f"      > Scrape Target: {url}")
        res = session.get(url, timeout=15)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')
        for s in soup(["script", "style"]): s.extract()
        clean_html = str(soup)[:30000]

        prompt = (
            "Extract a JSON list of animal rescues. Provide: 'name', 'city', 'state', 'website', 'email', 'phone'. "
            f"Source HTML:\n{clean_html}"
        )

        response = client.models.generate_content(
            model=MODEL_ID,
            contents=prompt,
            config=types.GenerateContentConfig(safety_settings=safety_settings, response_mime_type="application/json")
        )

        initial_data = json.loads(response.text.strip())
        final_entries = []
        for entry in initial_data:
            has_url = entry.get('website') and "http" in entry['website']
            missing_info = not entry.get('email') or not entry.get('phone')
            if has_url and missing_info:
                details = deep_scan_homepage(entry['name'], entry['website'])
                if details:
                    entry['email'] = details.get('email') or entry.get('email', "")
                    entry['phone'] = details.get('phone') or entry.get('phone', "")
            final_entries.append(entry)
        return final_entries
    except Exception as e:
        print(f"      [!] Error: {e}")
        return []


if __name__ == "__main__":
    states = ["New Jersey", "Northern Virginia", "Connecticut", "Maryland"]
    seen_names = set()  # To track duplicates in real-time

    print(f"[!] Results will be saved to {OUTPUT_FILE} in real-time.")

    # Open file in append mode
    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        for state in states:
            print(f"\n[+] STARTING STATE: {state}")
            query = f"list of animal rescues and shelters in {state} 2026"

            try:
                search = GoogleSearch({"q": query, "api_key": SERPAPI_KEY})
                links = [item.get("link") for item in search.get_dict().get("organic_results", [])]

                for link in links:
                    data = scrape_and_parse(link)
                    if data:
                        for entry in data:
                            name_key = entry.get('name', '').lower().strip()
                            if name_key and name_key not in seen_names:
                                # Write to .jsonl format
                                f.write(json.dumps(entry) + "\n")
                                f.flush()  # Force write to disk
                                seen_names.add(name_key)
                                print(f"        ✓ Saved: {entry.get('name')}")

                    time.sleep(2)
            except Exception as e:
                print(f"    [!] Search failed for {state}: {e}")

    print(f"\n[Done] Processed {len(seen_names)} unique rescues.")