import json
import os
import urllib.request
from playwright.sync_api import sync_playwright


class GoodSearchScraper:

    def __init__(self, headless: bool = True):
        self.headless = headless

    def _get_ip_via_doh(
        self, hostname: str = "www.goodsearch.com"
    ) -> str | None:
        """Resolves hostname to IP directly via Cloudflare DoH (1.1.1.1)."""
        try:
            req = urllib.request.Request(
                f"https://1.1.1.1/dns-query?name={hostname}&type=A",
                headers={"Accept": "application/dns-json"},
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode())
                for answer in data.get("Answer", []):
                    if answer.get("type") == 1:  # IPv4
                        return answer.get("data")
        except Exception as e:
            print(f"⚠️ DoH resolution failed: {e}")
        return None

    def _extract_deals_from_next_data(self, data: dict | list) -> list[dict]:
        """Recursively walks Next.js state tree to extract deal objects."""
        extracted = []
        seen_ids = set()

        title_keys = [
            "title",
            "description",
            "headline",
            "name",
            "text",
            "label",
            "tagline",
            "discount_title",
            "short_title",
        ]

        def search(node):
            if isinstance(node, dict):
                deal_id = (
                    node.get("id") or node.get("deal_id") or node.get("dealId")
                )
                code = (
                    node.get("code")
                    or node.get("coupon_code")
                    or node.get("couponCode")
                )

                if deal_id:
                    deal_str = str(deal_id)
                    if (
                        deal_str.isdigit()
                        and len(deal_str) >= 6
                        and deal_str not in seen_ids
                    ):
                        seen_ids.add(deal_str)

                        # Find first non-empty description string
                        title_text = "N/A"
                        for key in title_keys:
                            val = node.get(key)
                            if isinstance(val, str) and val.strip():
                                title_text = val.strip()
                                break

                        extracted.append(
                            {
                                "deal_id": deal_str,
                                "code": code if code else "NO CODE / DEAL ONLY",
                                "description": title_text,
                            }
                        )

                for value in node.values():
                    search(value)

            elif isinstance(node, list):
                for item in node:
                    search(item)

        search(data)
        return extracted

    def scrape_stores_from_jsonl(
        self, input_file: str, output_file: str
    ) -> None:
        if not os.path.exists(input_file):
            print(f"❌ Input file '{input_file}' not found.")
            return

        target_ip = self._get_ip_via_doh("www.goodsearch.com")
        launch_args = ["--ignore-certificate-errors"]

        if target_ip:
            print(f"🌐 Resolved via DoH -> {target_ip}")
            launch_args.append(
                f"--host-resolver-rules=MAP www.goodsearch.com {target_ip},"
                f" MAP goodsearch.com {target_ip}"
            )

        # Count lines for progress tracking
        with open(input_file, "r", encoding="utf-8") as f:
            total_stores = sum(1 for _ in f)

        print(
            f"🚀 Processing {total_stores} stores from '{input_file}' ->"
            f" '{output_file}'\n"
        )

        with sync_playwright() as p:
            # Launch browser once for all requests
            browser = p.chromium.launch(
                headless=self.headless, args=launch_args
            )
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            )
            page = context.new_page()

            # Block unnecessary network assets to speed up execution
            page.route(
                "**/*.{png,jpg,jpeg,svg,css,woff,woff2}",
                lambda route: route.abort(),
            )

            with (
                open(input_file, "r", encoding="utf-8") as in_f,
                open(output_file, "w", encoding="utf-8") as out_f,
            ):

                for idx, line in enumerate(in_f, 1):
                    line = line.strip()
                    if not line:
                        continue

                    store_data = json.loads(line)
                    url = store_data.get("url")
                    name = store_data.get("name", "Unknown Store")

                    print(f"[{idx}/{total_stores}] Fetching {name} ({url})...")

                    coupons = []
                    try:
                        page.goto(
                            url, wait_until="domcontentloaded", timeout=15000
                        )
                        next_data = page.locator("script#__NEXT_DATA__")

                        if next_data.count() > 0:
                            raw_json = json.loads(next_data.inner_text())
                            coupons = self._extract_deals_from_next_data(
                                raw_json
                            )
                        else:
                            print("  ⚠️ Script tag __NEXT_DATA__ not found.")

                    except Exception as e:
                        print(f"  ❌ Error fetching {name}: {e}")

                    # Build the enriched output object
                    record = {
                        "id": store_data.get("id"),
                        "name": name,
                        "slug": store_data.get("slug"),
                        "url": url,
                        "total_coupons": len(coupons),
                        "coupons": coupons,  # Nested JSON block with coupons
                    }

                    # Write and flush immediately
                    out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    out_f.flush()

                    print(f"  └─ Extracted {len(coupons)} coupons.")

            browser.close()

        print(f"\n✅ Scraping finished! Output written to '{output_file}'.")


if __name__ == "__main__":
    scraper = GoodSearchScraper(headless=True)
    scraper.scrape_stores_from_jsonl(
        input_file="stores.jsonl", output_file="stores_with_coupons.jsonl"
    )