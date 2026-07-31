import time
import requests

# Target output file path
output_file = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/substack/posts_allrisesd.substack.com.txt"

domain = "https://allrisesd.substack.com/"
api_url = f"{domain}/api/v1/posts"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

all_links = []
limit = 50
offset = 0

print("Fetching full post list from Substack API...")

while True:
    params = {
        "sort": "new",
        "offset": offset,
        "limit": limit
    }

    try:
        response = requests.get(api_url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        posts = response.json()

        # If the API returns an empty list or isn't a list, we've hit the end
        if not posts or not isinstance(posts, list):
            break

        batch_count = len(posts)

        for post in posts:
            link = post.get("canonical_url")
            if not link and post.get("slug"):
                link = f"{domain}/p/{post.get('slug')}"

            if link and link not in all_links:
                all_links.append(link)

        print(f"Retrieved {len(all_links)} unique post links so far...")

        # If we got fewer items than the limit, we've reached the last page
        if batch_count < limit:
            break

        offset += limit
        time.sleep(0.4)  # Gentle pacing

    except Exception as e:
        print(f"Error fetching page at offset {offset}: {e}")
        break

# Write all collected post URLs to the specified text file
with open(output_file, "w", encoding="utf-8") as f:
    for link in all_links:
        f.write(f"{link}\n")

print(f"\nDone! Successfully wrote all {len(all_links)} post URLs to:")
print(output_file)