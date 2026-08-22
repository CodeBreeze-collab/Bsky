import csv
import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

# File Paths
CSV_FILE_PATH = '/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/igive/igive_stores_categorized.csv'
OUTPUT_JSONL_PATH = '/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/igive/igive_stores_with_products.jsonl'

# Common URL paths that indicate a product page
PRODUCT_INDICATORS = ['/product/', '/p/', '/item/', '/dp/', '/shop/']


def get_sample_products(store_url, max_samples=3):
    samples = set()
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36'
        }

        response = requests.get(store_url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')

        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']

            if any(indicator in href.lower() for indicator in PRODUCT_INDICATORS):
                full_url = urljoin(store_url, href)

                # Ensure the link stays on the same domain
                if urlparse(full_url).netloc == urlparse(store_url).netloc:
                    samples.add(full_url)

                    if len(samples) >= max_samples:
                        break

    except Exception as e:
        print(f"  [!] Error connecting to {store_url}: {e}")

    return list(samples)


def process_csv():
    # Open the input CSV for reading, and the new JSONL file for writing
    with open(CSV_FILE_PATH, mode='r', encoding='utf-8') as infile, \
            open(OUTPUT_JSONL_PATH, mode='w', encoding='utf-8') as outfile:

        reader = csv.reader(infile)

        for row in reader:
            # Skip malformed or empty rows
            if len(row) < 5:
                continue

            store_name = row[0]
            category = row[1]
            percentage = row[2]
            igive_url = row[3]
            store_url = row[4]

            print(f"Scraping: {store_name} ({store_url})")

            # Scrape up to 3 product URLs
            product_urls = get_sample_products(store_url)

            # Construct a dictionary for the JSON object
            store_data = {
                "store_name": store_name,
                "category": category,
                "percentage": percentage,
                "igive_url": igive_url,
                "store_url": store_url,
                "sample_product_urls": product_urls  # This will be safely stored as a JSON array
            }

            # Convert dictionary to JSON string and write it with a newline
            outfile.write(json.dumps(store_data) + '\n')

            # Force the system to write to disk immediately (Real-time saving)
            outfile.flush()

            # Console output for tracking progress
            for url in product_urls:
                print(f"  -> {url}")
            print("-" * 40)


if __name__ == "__main__":
    process_csv()