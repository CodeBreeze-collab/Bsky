import json
import socket
import time
from bs4 import BeautifulSoup
import requests


# --- DoH System DNS Bypass ---
def get_ip_via_doh(hostname):
    try:
        url = "https://1.1.1.1/dns-query"
        headers = {"accept": "application/dns-json"}
        res = requests.get(
            url,
            headers=headers,
            params={"name": hostname, "type": "A"},
            timeout=5,
        )
        for answer in res.json().get("Answer", []):
            if answer.get("type") == 1:
                return answer["data"]
    except Exception:
        pass
    return None


target_domain = "www.goodsearch.com"
resolved_ip = get_ip_via_doh(target_domain)

if resolved_ip:
    _orig_getaddrinfo = socket.getaddrinfo

    def custom_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        if host in [target_domain, "goodsearch.com"]:
            return _orig_getaddrinfo(
                resolved_ip, port, family, type, proto, flags
            )
        return _orig_getaddrinfo(host, port, family, type, proto, flags)

    socket.getaddrinfo = custom_getaddrinfo

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

all_stores = []
seen_ids = set()


def add_merchants(merchant_list, page_num, file_handle):
    added = 0
    for merchant in merchant_list:
        m_id = merchant.get("id")
        if m_id and m_id not in seen_ids:
            seen_ids.add(m_id)
            slug = merchant.get("customSlug") or merchant.get("slug")
            name = merchant.get("name")
            store_url = f"https://www.goodsearch.com/coupons/{slug}"

            store_record = {
                "id": m_id,
                "name": name,
                "slug": slug,
                "url": store_url,
                "page": page_num,
            }

            all_stores.append(store_record)
            added += 1

            # Console log in real-time
            print(f"  [{len(all_stores)}] {name} -> {store_url}")

            # Stream JSON Lines record directly to disk
            file_handle.write(
                json.dumps(store_record, ensure_ascii=False) + "\n"
            )
            file_handle.flush()  # Force immediate write to disk

    return added


def extract_next_data(html_text):
    soup = BeautifulSoup(html_text, "html.parser")
    next_script = soup.find("script", id="__NEXT_DATA__")
    if next_script and next_script.string:
        return json.loads(next_script.string)
    return None


# --- Scraping Loop ---
page = 1
total_pages = None
output_file_path = "stores.jsonl"

print(f"Starting scraper... Streaming results to: {output_file_path}\n")

# Open JSONL file in write mode
with open(output_file_path, "w", encoding="utf-8") as file_handle:
    while True:
        url = (
            "https://www.goodsearch.com/sitemap"
            if page == 1
            else f"https://www.goodsearch.com/sitemap/{page}"
        )
        print(f"--- Fetching Page {page} ({url}) ---")

        try:
            res = requests.get(url, headers=headers, timeout=10)

            if res.status_code != 200:
                print(
                    f"Returned HTTP {res.status_code}. Stopping pagination."
                )
                break

            data = extract_next_data(res.text)
            if not data:
                print(f"Failed to extract __NEXT_DATA__ from page {page}.")
                break

            page_props = data.get("props", {}).get("pageProps", {})
            merchant_list = page_props.get("merchantList", [])

            if not merchant_list:
                print(f"No merchants found on Page {page}. Scraping finished.")
                break

            # Print and stream JSON records for this page
            added = add_merchants(merchant_list, page, file_handle)

            if added == 0:
                print("Duplicate content detected. Stopping.")
                break

            # Check total pages on initial run
            if total_pages is None:
                pagination = page_props.get("pagination", {})
                total_pages = (
                    pagination.get("totalPages")
                    or pagination.get("pageCount")
                    or pagination.get("pages")
                )
                if total_pages:
                    print(f"Total pages reported by server: {total_pages}\n")

            if total_pages and page >= int(total_pages):
                print(f"\nReached total page limit of {total_pages}!")
                break

            page += 1
            time.sleep(0.5)

        except Exception as e:
            print(f"Error fetching page {page}: {e}")
            break

print(
    f"\nDone! Extracted {len(all_stores)} total stores into"
    f" '{output_file_path}'."
)