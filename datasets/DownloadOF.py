import socket
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup


def get_ip_via_doh(hostname):
    """Query Cloudflare's 1.1.1.1 directly by IP to resolve hostnames without relying on system DNS."""
    try:
        url = "https://1.1.1.1/dns-query"
        headers = {"accept": "application/dns-json"}
        params = {"name": hostname, "type": "A"}

        res = requests.get(url, headers=headers, params=params, timeout=5)
        data = res.json()

        for answer in data.get("Answer", []):
            if answer.get("type") == 1:  # Type 1 = IPv4 Address
                return answer["data"]
    except Exception as e:
        print(f"DoH resolution failed: {e}")
    return None


target_domain = "www.goodsearch.com"
resolved_ip = get_ip_via_doh(target_domain)

if not resolved_ip:
    print(f"Could not resolve IP for {target_domain}.")
    exit(1)

print(f"Resolved {target_domain} -> {resolved_ip} via DoH")

# Override socket.getaddrinfo so requests connects directly to the resolved IP
# while keeping SSL/TLS handshakes and SNI intact.
_orig_getaddrinfo = socket.getaddrinfo


def custom_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if host in [target_domain, "goodsearch.com"]:
        return _orig_getaddrinfo(
            resolved_ip, port, family, type, proto, flags
        )
    return _orig_getaddrinfo(host, port, family, type, proto, flags)


socket.getaddrinfo = custom_getaddrinfo

# Fetch and scrape the sitemap
url = "https://www.goodsearch.com/sitemap"
headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

try:
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    store_links = []

    # Find all <a> tags where href contains coupon store paths
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]

        if href.startswith("/coupons/"):
            # Clean up text (e.g. "Walmart Codes")
            store_name = " ".join(a_tag.stripped_strings)
            full_url = urljoin("https://www.goodsearch.com", href)

            store_links.append({"store": store_name, "url": full_url})

    print(f"\nSuccessfully extracted {len(store_links)} store links!\n")

    # Display sample results
    for item in store_links[:15]:
        print(f"Store: {item['store']:<30} -> {item['url']}")
except Exception as e:
    print(f"Failed to fetch sitemap: {e}")