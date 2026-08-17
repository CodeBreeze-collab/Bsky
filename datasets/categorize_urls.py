import os
import re
import json
import requests
from bs4 import BeautifulSoup
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from typing import List

# Initialize the Gemini client
client = genai.Client()


# Define output structure
class CategoryItem(BaseModel):
    url: str = Field(description="The original URL or domain name.")
    category: str = Field(
        description="Inferred primary product category (e.g., Clothes, Electronics, Fitness, Home Decor, Work Shoes, etc., or 'Unknown' if unclear).")
    reasoning: str = Field(description="A brief explanation for the category choice.")


class BatchCategorization(BaseModel):
    results: List[CategoryItem]


def clean_url_line(line):
    """Removes citation tags, backslashes, and surrounding whitespace."""
    line = line.replace('\\', '')
    return line.strip()

def load_urls(filename):
    """Reads the text file and returns a list of valid, cleaned URLs/domains."""
    if not os.path.exists(filename):
        raise FileNotFoundError(f"Could not find {filename}. Please save the URLs there.")
    urls = []
    with open(filename, 'r', encoding='utf-8') as f:
        for line in f:
            cleaned = clean_url_line(line)
            if cleaned:
                urls.append(cleaned)
    return urls


def batch_urls(url_list, batch_size=20):
    """Yields successive batches from the url list."""
    for i in range(0, len(url_list), batch_size):
        yield url_list[i:i + batch_size]


def prefetch_metadata(url):
    """Fetches title, meta description, and top headings from a URL homepage."""
    target_url = url if url.startswith(('http://', 'https://')) else f'https://{url}'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
    }

    try:
        response = requests.get(target_url, headers=headers, timeout=5)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')

            # Extract Title
            title = soup.title.string.strip() if soup.title and soup.title.string else ""

            # Extract Meta Description
            meta_desc = ""
            desc_tag = soup.find('meta', attrs={'name': lambda x: x and x.lower() == 'description'})
            if desc_tag and desc_tag.get('content'):
                meta_desc = desc_tag['content'].strip()

            # Extract H1/H2 Headings for extra keyword context
            headings = []
            for h in soup.find_all(['h1', 'h2'], limit=3):
                h_text = h.get_text().strip()
                if h_text and len(h_text) < 100:
                    headings.append(h_text)

            return {
                "url": url,
                "title": title,
                "description": meta_desc,
                "headings": " | ".join(headings),
                "success": True
            }
    except Exception:
        pass  # Fallback gracefully if blocked or offline

    return {"url": url, "title": "", "description": "", "headings": "", "success": False}


def categorize_batch(batch_data):
    """Sends a batch of pre-scraped store metadata to Gemini with fallback rules."""
    prompt = (
        "You are an e-commerce data assistant. For each store below, I have provided its URL, "
        "along with scraped homepage metadata (Title, Description, and Headings).\n\n"
        "Instructions:\n"
        "1. Infer its primary product category based on the provided metadata.\n"
        "2. If metadata is missing, empty, or failed to load (marked as N/A), **fall back to analyzing the URL/domain name itself** to make your best educated guess.\n"
        "3. Only mark as 'Unknown' if neither the metadata nor the domain name provides any clues.\n\n"
        "Stores:\n"
    )

    for item in batch_data:
        prompt += f"- URL: {item['url']}\n"
        prompt += f"  Title: {item['title'] or 'N/A'}\n"
        prompt += f"  Description: {item['description'] or 'N/A'}\n"
        prompt += f"  Headings: {item['headings'] or 'N/A'}\n\n"

    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=BatchCategorization,
            temperature=0.1
        ),
    )

    data = json.loads(response.text)
    return data.get("results", [])


def main():
    input_filename = '/Users/hdon/Desktop/go-affpro-pages/instant_approval_stores.txt'
    output_filename = '/Users/hdon/Desktop/go-affpro-pages/categorized_stores_3.jsonl'

    try:
        urls = load_urls(input_filename)
    except Exception as e:
        print(e)
        return

    batch_size = 15
    print(f"Loaded {len(urls)} URLs. Processing with smart pre-fetching in batches of {batch_size}...\n")

    with open(output_filename, 'a', encoding='utf-8') as outfile:
        for i, batch in enumerate(batch_urls(urls, batch_size)):
            batch_num = i + 1
            print(
                f"=== Processing Batch {batch_num} (Items {i * batch_size + 1} to {min((i + 1) * batch_size, len(urls))}) ===")

            # Step 1: Prefetch metadata & headings
            batch_metadata = [prefetch_metadata(url) for url in batch]

            try:
                # Step 2: Send metadata + domain fallback context to Gemini
                categorized_items = categorize_batch(batch_metadata)

                # Step 3: Write results real-time to JSONL
                for item in categorized_items:
                    outfile.write(json.dumps(item) + '\n')
                outfile.flush()

                print(f"Successfully processed and saved {len(categorized_items)} items.")
                print("-" * 40)

            except Exception as e:
                print(f"Error processing batch {batch_num}: {e}\n")

    print(f"\nProcessing complete! Results saved to {output_filename}")


if __name__ == '__main__':
    main()