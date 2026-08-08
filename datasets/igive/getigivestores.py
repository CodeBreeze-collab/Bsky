import csv
import json
import re
import requests
from bs4 import BeautifulSoup


def fetch_all_igive_stores():
    url = "https://www.igive.com/html/merchantlist2.cfm"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    response = requests.get(url, headers=headers)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    stores = []

    # Non-merchant utility URL paths to exclude
    ignored_paths = [
        "/app", "/button", "/welcome", "/html/", "/index.cfm",
        "causes.igive.com", "itunes.apple.com", "facebook.com",
        "twitter.com", "support", "privacy", "terms", "about"
    ]

    # Target table rows (tr) containing store listings
    rows = soup.find_all("tr")

    for row in rows:
        anchor = row.find("a", href=True)
        if not anchor:
            continue

        href = anchor["href"]
        store_name = anchor.get_text(strip=True)

        # Ignore utility links and table header titles
        if any(ignored in href.lower() for ignored in ignored_paths):
            continue
        if store_name.lower() in ["online store", "vendor details", "details", "icon", "login", ""]:
            continue

        # Extract row text to capture donation rate (e.g., "2.8%", "12.0%", "Special Rate")
        row_text = row.get_text(" ", strip=True)
        rate_match = re.search(r'(\d+(?:\.\d+)?%\s*|\bSpecial Rate\b)', row_text, re.IGNORECASE)
        donation_rate = rate_match.group(1).strip() if rate_match else "N/A"

        full_url = href if href.startswith("http") else f"https://www.igive.com{href}"

        stores.append({
            "store_name": store_name,
            "igive_url": full_url,
            "donation_rate": donation_rate
        })

    # Deduplicate entries by URL while preserving list order
    seen_urls = set()
    unique_stores = []
    for store in stores:
        if store["igive_url"] not in seen_urls:
            seen_urls.add(store["igive_url"])
            unique_stores.append(store)

    return unique_stores


def save_to_csv(stores, filename="igive_stores.csv"):
    with open(filename, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["store_name", "igive_url", "donation_rate"])
        writer.writeheader()
        writer.writerows(stores)


if __name__ == "__main__":
    store_list = fetch_all_igive_stores()
    print(f"Extracted {len(store_list)} stores.")

    save_to_csv(store_list)
    print("Saved full directory to igive_stores.csv")

    print("\nSample Output:")
    print(json.dumps(store_list[:5], indent=2))