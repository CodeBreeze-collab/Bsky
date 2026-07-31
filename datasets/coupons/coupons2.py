import json
import urllib.request
from playwright.sync_api import sync_playwright


class GoodSearchScraper:
    def __init__(self, url: str = "https://www.goodsearch.com/coupons/petsandfriends.co.uk", headless: bool = True):
        self.url = url
        self.headless = headless

    def _get_ip_via_doh(self, hostname: str = "www.goodsearch.com") -> str | None:
        """Resolves hostname to IP directly via Cloudflare DoH (1.1.1.1)."""
        try:
            req = urllib.request.Request(
                f"https://1.1.1.1/dns-query?name={hostname}&type=A",
                headers={"Accept": "application/dns-json"}
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode())
                if "Answer" in data:
                    for answer in data["Answer"]:
                        if answer.get("type") == 1:
                            return answer.get("data")
        except Exception:
            pass
        return None

    def _extract_deals_from_next_data(self, data: dict | list) -> list[dict]:
        """Recursively parses Next.js state to extract all deal objects."""
        extracted = []
        seen_ids = set()

        def search(node):
            if isinstance(node, dict):
                # Check for standard deal/coupon dictionary keys
                deal_id = node.get("id") or node.get("deal_id") or node.get("dealId")
                code = node.get("code") or node.get("coupon_code") or node.get("couponCode")
                title = node.get("title") or node.get("description") or node.get("heading") or "N/A"

                if deal_id and str(deal_id) not in seen_ids:
                    # Valid deal items usually have numeric/string deal IDs and codes/discount details
                    deal_str = str(deal_id)
                    if deal_str.isdigit() and len(deal_str) >= 6:
                        seen_ids.add(deal_str)
                        extracted.append({
                            "deal_id": deal_str,
                            "code": code if code else "NO CODE / DEAL ONLY",
                            "title": title
                        })

                for value in node.values():
                    search(value)

            elif isinstance(node, list):
                for item in node:
                    search(item)

        search(data)
        return extracted

    def get_coupon_codes(self) -> list[dict]:
        target_ip = self._get_ip_via_doh("www.goodsearch.com")
        launch_args = ["--ignore-certificate-errors"]
        if target_ip:
            launch_args.append(
                f'--host-resolver-rules=MAP www.goodsearch.com {target_ip}, MAP goodsearch.com {target_ip}'
            )

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless, args=launch_args)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            print(f"Navigating to {self.url}...")
            page.goto(self.url, wait_until="domcontentloaded")

            # Extract __NEXT_DATA__ script contents
            next_data_elem = page.locator('script#__NEXT_DATA__')
            if next_data_elem.count() == 0:
                print("❌ Could not locate script#__NEXT_DATA__ tag.")
                browser.close()
                return []

            raw_json = json.loads(next_data_elem.inner_text())
            coupons = self._extract_deals_from_next_data(raw_json)

            browser.close()
            return coupons


if __name__ == "__main__":
    scraper = GoodSearchScraper(headless=True)
    results = scraper.get_coupon_codes()

    print(f"\nExtraction Complete ({len(results)} coupons found):")
    for idx, deal in enumerate(results, 1):
        print(f"[{idx}/{len(results)}] Deal #{deal['deal_id']} -> Code: {deal['code']} | Title: {deal['title']}")