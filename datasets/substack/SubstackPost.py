import json
import time
import requests
from bs4 import BeautifulSoup

S = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/substack/"

BSKY_DATASETS_SUBSTACK_ = "%s" % S


def process_urls_file(input_txt_file="posts_allrisesd.substack.com.txt", output_jsonl_file="allrisesd_substack_posts.jsonl"):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    # Read URLs from input text file (ignoring empty lines and comments)
    with open(input_txt_file, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    print(f"Found {len(urls)} URLs/slugs to process...")

    successful_count = 0

    # Open the JSONL file in append mode
    with open(output_jsonl_file, "a", encoding="utf-8") as jsonl_file:
        for url_or_slug in urls:
            # Parse publication domain and slug from URL
            # Handles formats like:
            # - https://housingny.substack.com/p/nyaa-recommendations-may-become-law
            # - https://customdomain.com/p/some-post-slug
            if "http://" in url_or_slug or "https://" in url_or_slug:
                parts = url_or_slug.rstrip("/").split("/p/")
                base_domain = parts[0]
                slug = parts[1].split("?")[0] if len(parts) > 1 else ""
                api_url = f"{base_domain}/api/v1/posts/{slug}"
            else:
                # Default to housingny.substack.com if only a slug is provided
                slug = url_or_slug.strip("/")
                api_url = f"https://housingny.substack.com/api/v1/posts/{slug}"

            try:
                # Fetch post data from Substack API
                res = requests.get(api_url, headers=headers, timeout=10)
                res.raise_for_status()
                data = res.json()

                # Extract and clean post body HTML into readable plain text
                html_body = data.get("body_html", "")
                plain_text = ""
                if html_body:
                    soup = BeautifulSoup(html_body, "html.parser")
                    tags = soup.find_all(["p", "h1", "h2", "h3", "h4", "li", "blockquote"])
                    plain_text = "\n\n".join([t.get_text(strip=True) for t in tags if t.get_text(strip=True)])

                # Build JSON record
                post_record = {
                    "id": data.get("id"),
                    "title": data.get("title"),
                    "subtitle": data.get("subtitle"),
                    "slug": data.get("slug"),
                    "post_date": data.get("post_date"),
                    "canonical_url": data.get("canonical_url"),
                    "author": data.get("publishedBylines", [{}])[0].get("name") if data.get("publishedBylines") else None,
                    "cover_image": data.get("cover_image"),
                    "body_text": plain_text,
                    "body_html": html_body
                }

                # Write single JSON line (\n) to JSONL file
                jsonl_file.write(json.dumps(post_record, ensure_ascii=False) + "\n")
                successful_count += 1
                print(f"[✓] Processed: {post_record.get('title')}")

            except Exception as e:
                print(f"[X] Failed processing {url_or_slug}: {e}")

            # Polite delay between requests to prevent hitting rate limits
            time.sleep(0.5)

    print(f"\nDone! Successfully saved {successful_count}/{len(urls)} posts to {output_jsonl_file}")


# Run the batch processor
if __name__ == "__main__":
    process_urls_file("%sposts_allrisesd.substack.com.txt" % S,
                      "%sallrisesd_substack_posts.jsonl" % S)