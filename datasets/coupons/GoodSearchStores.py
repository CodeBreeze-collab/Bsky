from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

# Try alternative domains if one fails to resolve
target_urls = [
    "https://goodsearch.com/sitemap",
    "https://www.goodshop.com/sitemap",
]

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

response = None
working_url = None

for url in target_urls:
    try:
        print(f"Trying {url}...")
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()
        response = res
        working_url = url
        break
    except requests.exceptions.RequestException as e:
        print(f"Failed to reach {url}: {e}")

if response:
    print(f"\nSuccessfully connected to {working_url}!\n")
    soup = BeautifulSoup(response.text, "html.parser")

    store_links = []
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if href.startswith("/coupons/"):
            store_name = " ".join(a_tag.stripped_strings)
            full_url = urljoin(working_url, href)
            store_links.append({"name": store_name, "url": full_url})

    print(f"Total store links found: {len(store_links)}")
    for store in store_links[:10]:
        print(f"Store: {store['name']} -> {store['url']}")
else:
    print("\nCould not resolve or connect to any specified target URLs.")