import csv
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup

INPUT_CSV = "igive_stores_verified.csv"
OUTPUT_CSV = "igive_stores_with_categories.csv"

MAX_WORKERS = 20  # Parallel HTTP requests
TIMEOUT = 5

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# Fallback category mapping rules based on store name keywords
CATEGORY_KEYWORDS = {
    "Pets & Animal Care": ["pet", "dog", "cat", "vet", "animal", "chewy", "bark"],
    "Apparel & Fashion": ["apparel", "clothing", "wear", "shoes", "boutique", "fashion", "jeans", "outfitters"],
    "Health & Beauty": ["beauty", "cosmetics", "pharmacy", "vitamin", "health", "skin", "hair", "wellness",
                        "fragrance"],
    "Computers & Electronics": ["electronics", "tech", "computer", "software", "vpn", "photo", "audio", "mobile",
                                "wireless"],
    "Home & Living": ["home", "furniture", "bed", "decor", "kitchen", "mattress", "hardware", "lighting", "bath"],
    "Travel & Lodging": ["hotel", "resort", "travel", "flight", "airline", "cruise", "vacation", "car rental"],
    "Food & Gourmet": ["food", "basket", "florist", "flower", "wine", "gourmet", "snack", "meat", "bakery"],
    "Sports & Outdoors": ["sports", "outdoor", "gear", "fitness", "golf", "cycle", "hunting", "fishing"],
    "Books, Media & Toys": ["book", "toy", "game", "media", "education", "learning", "kids"],
}


def infer_category_from_name(store_name):
    """Fallback rule-based category classifier."""
    name_lower = store_name.lower()
    for cat, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in name_lower for kw in keywords):
            return cat
    return "General Retail & Shopping"


def fetch_igive_category(store_row):
    """Fetches the official category tag directly from the iGive store landing page."""
    store_name = store_row.get("store_name", "").strip()
    igive_url = store_row.get("igive_url", "").strip()
    rate = store_row.get("donation_rate", "").strip()
    actual_url = store_row.get("actual_store_url", "").strip()

    category = None

    try:
        resp = requests.get(igive_url, headers=HEADERS, timeout=TIMEOUT)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")

            # 1. Look for meta keywords / meta description
            meta_desc = soup.find("meta", attrs={"name": "description"})
            meta_kw = soup.find("meta", attrs={"name": "keywords"})

            meta_text = ""
            if meta_desc and meta_desc.get("content"):
                meta_text += meta_desc["content"] + " "
            if meta_kw and meta_kw.get("content"):
                meta_text += meta_kw["content"]

            # 2. Look for breadcrumbs or explicit category label elements
            cat_elem = soup.find(
                lambda tag: tag.name in ["span", "a", "div", "li"] and "category" in tag.get("class", []))
            if cat_elem:
                category = cat_elem.text.strip()

            # 3. If meta text mentions category keyword, match it
            if not category and meta_text:
                for cat, kws in CATEGORY_KEYWORDS.items():
                    if any(kw in meta_text.lower() for kw in kws):
                        category = cat
                        break
    except Exception:
        pass

    # If scraping didn't find an explicit tag, use rule-based inference
    if not category or category.lower() in ["unknown", "n/a", ""]:
        category = infer_category_from_name(store_name)

    return {
        "store_name": store_name,
        "category": category,
        "donation_rate": rate,
        "igive_url": igive_url,
        "actual_store_url": actual_url,
    }


def main():
    if not os.path.exists(INPUT_CSV):
        print(f"Error: '{INPUT_CSV}' not found. Run the domain resolution script first.")
        sys.exit(1)

    with open(INPUT_CSV, mode="r", encoding="utf-8") as infile:
        stores = list(csv.DictReader(infile))

    total = len(stores)
    print(f"Loaded {total} stores from '{INPUT_CSV}'. Extracting categories...\n")

    start_time = time.time()
    results = []
    completed = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(fetch_igive_category, row): row for row in stores}
        for future in as_completed(futures):
            res = future.result()
            results.append(res)
            completed += 1

            if completed % 100 == 0 or completed == total:
                elapsed = time.time() - start_time
                print(f"[{completed}/{total}] '{res['store_name']}' -> [{res['category']}] ({elapsed:.1f}s)")

    results_sorted = sorted(results, key=lambda x: x["store_name"].lower())

    fieldnames = ["store_name", "category", "donation_rate", "igive_url", "actual_store_url"]
    with open(OUTPUT_CSV, mode="w", newline="", encoding="utf-8") as outfile:
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results_sorted)

    print(f"\nDone! Updated {total} stores with categories in {time.time() - start_time:.1f}s.")
    print(f"Saved dataset to '{OUTPUT_CSV}'.")


if __name__ == "__main__":
    main()