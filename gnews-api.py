import requests
import json
import time

# Configuration
API_KEY = '8f41d5d8f5e8414236566c235f9d3153'
QUERY = '"Miami"'
OUTPUT_FILE = 'miami_complete.jsonl'
MAX_PAGES = 10  # GNews free tier typically allows 100 total results (10 pages)


def fetch_all_pages():
    total_articles_saved = 0

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        for page in range(1, MAX_PAGES + 1):
            print(f"Fetching page {page}...")

            # Note: We use the 'page' parameter to paginate
            url = f"https://gnews.io/api/v4/search?q={QUERY}&lang=en&page={page}&apikey={API_KEY}"

            response = requests.get(url)

            if response.status_code == 200:
                data = response.json()
                articles = data.get('articles', [])

                if not articles:
                    print("No more articles found. Stopping.")
                    break

                for article in articles:
                    # Add a small metadata tag so you know which page it came from
                    article['extracted_from_page'] = page
                    f.write(json.dumps(article, ensure_ascii=False) + '\n')

                total_articles_saved += len(articles)

                # Ethical Delay: Best practice to not spam the server
                time.sleep(1)

            elif response.status_code == 403:
                print("Reached API limit or restricted page. Stopping.")
                break
            else:
                print(f"Error {response.status_code}: {response.text}")
                break

    print(f"🏁 Finished! Saved {total_articles_saved} articles to {OUTPUT_FILE}")


if __name__ == "__main__":
    fetch_all_pages()