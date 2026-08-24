import json
import time
import requests
from bs4 import BeautifulSoup

# File paths
input_file = '/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/igive/igive_stores_with_products.jsonl'
output_file = '/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/igive/igive_stores_with_products_enriched.jsonl'

# Headers to mimic a real browser and avoid blocks
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
}


def fetch_description(url, store_name):
    """Fetches the URL, follows redirects, and extracts the description."""
    try:
        # Requests automatically follows redirects (like the search.cfm expansion)
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # Heuristic 1: Find a header containing the store name, grab the next paragraph
        # (You will need to inspect the actual webpage DOM to get the exact class/tag if this fails)
        headers = soup.find_all(['h1', 'h2', 'h3', 'h4'])
        for header in headers:
            if store_name.lower() in header.get_text().lower():
                # Look for the next sibling that is a paragraph or div containing text
                nxt = header.find_next_sibling(['p', 'div'])
                if nxt:
                    return nxt.get_text(strip=True)

        # Fallback if specific structure isn't found
        return "Description not found on page."

    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return "Error fetching description."


def process_jsonl():
    print("Starting enrichment process...")

    with open(input_file, 'r', encoding='utf-8') as infile, \
            open(output_file, 'w', encoding='utf-8') as outfile:

        for line_num, line in enumerate(infile, 1):
            if not line.strip():
                continue

            data = json.loads(line)
            igive_url = data.get("igive_url")
            store_name = data.get("store_name")

            print(f"Processing line {line_num}: {store_name}")

            if igive_url:
                description = fetch_description(igive_url, store_name)
                data["description"] = description
            else:
                data["description"] = ""

            # Write the updated JSON object to the new file
            json.dump(data, outfile)
            outfile.write('\n')
            outfile.flush()

            # Be polite to the server: wait 1 second between requests
            time.sleep(1)

    print(f"Finished! Enriched data saved to {output_file}")


if __name__ == "__main__":
    process_jsonl()