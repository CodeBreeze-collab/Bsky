import json
import os
import time
from playwright.sync_api import sync_playwright


def is_valid_url(url: str) -> bool:
    """Returns False if the URL is a static asset or a known analytics/tracking link."""
    url_lower = url.lower()

    # 1. Filter out analytics, trackers, and consent scripts
    ignored_keywords = [
        "google-analytics.com",
        "googletagmanager.com",
        "trustarc.com",
        "authiframe",
    ]

    if any(keyword in url_lower for keyword in ignored_keywords):
        return False

    # 2. Strip query params (?) and fragments (#) to inspect file extension
    clean_path = url_lower.split("?")[0].split("#")[0]
    ignored_extensions = (
        ".png",
        ".js",
        ".svg",
        ".css",
        ".woff2",
        ".gif",
        ".ico",
        ".jpg",
        ".jpeg",
    )

    return not clean_path.endswith(ignored_extensions)


def process_store(context, store_data: dict) -> list[str]:
    """Navigates to a store page, interacts with coupon buttons, and extracts outbound links."""
    url = store_data.get("url")
    slug = store_data.get("slug", "")

    # Extract store keyword from slug (e.g., 'lanebryant.com' -> 'lanebryant')
    store_keyword = slug.split(".")[0].lower() if slug else ""

    outbound_requests = []

    # Dynamic search keywords for tracking
    tracking_keywords = ["/out/", "redirect", "affiliate", "click"]
    if store_keyword:
        tracking_keywords.append(store_keyword)

    def track_requests(req):
        if any(kw in req.url.lower() for kw in tracking_keywords):
            outbound_requests.append(req.url)

    context.on("request", track_requests)
    page = context.new_page()

    print(f"\n🌐 Navigating to [{store_data.get('name')}]: {url}")
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)

    # 1. Click primary "Show code" button
    initial_button = page.locator(
        "button:has-text('Show code'), a:has-text('Show code')"
    ).first

    if initial_button.count() > 0:
        print("  🖱️ Step 1: Clicking primary 'Show code' button...")
        try:
            with context.expect_page(timeout=10000) as deal_tab_info:
                initial_button.click(no_wait_after=True)

            deal_tab = deal_tab_info.value
            deal_tab.wait_for_load_state("domcontentloaded")
            deal_tab.wait_for_timeout(2000)

            # 2. Click secondary [Copy Code] button
            copy_button = deal_tab.locator(
                "button:has-text('Copy'), a:has-text('Copy')"
            ).first

            if copy_button.count() > 0:
                print("  🖱️ Step 2: Clicking [Copy Code] button...")
                try:
                    with deal_tab.expect_popup(timeout=5000) as popup_info:
                        copy_button.click(no_wait_after=True)
                    popup_info.value.wait_for_load_state("domcontentloaded")
                except Exception:
                    time.sleep(3)
            else:
                print("  ❌ Could not locate [Copy Code] button on deal tab.")
        except Exception as e:
            print(f"  ⚠️ Error during step interaction: {e}")
    else:
        print("  ❌ Could not locate 'Show code' button.")

    # Deduplicate and apply URL validation filter
    filtered_links = [
        link
        for link in sorted(list(set(outbound_requests)))
        if is_valid_url(link)
    ]

    page.close()
    return filtered_links


def process_coupons_jsonl(input_file: str, output_file: str) -> None:
    """Reads store targets from input JSONL, fetches captured links, and writes to output JSONL in real time."""
    if not os.path.exists(input_file):
        print(f"❌ Input file not found: {input_file}")
        return

    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    # Load store entries
    stores = []
    with open(input_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                stores.append(json.loads(line.strip()))

    print(f"📋 Loaded {len(stores)} store(s) from input JSONL.")

    with sync_playwright() as p:
        # Running in headless mode in the background
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-popup-blocking"],
        )

        # Open output file in append/write mode to stream lines iteratively
        with open(output_file, "a", encoding="utf-8") as out_f:
            for index, store in enumerate(stores, start=1):
                print(f"\n--- Store [{index}/{len(stores)}]: {store.get('name')} ---")

                # New isolated context per store to prevent cookie/session leakage
                context = browser.new_context(
                    permissions=["clipboard-read", "clipboard-write"],
                )

                try:
                    captured_links = process_store(context, store)
                    store["captured_links"] = captured_links
                    print(f"  💾 Captured {len(captured_links)} link(s).")
                except Exception as err:
                    print(f"  ❌ Failed processing {store.get('name')}: {err}")
                    store["captured_links"] = []
                finally:
                    context.close()

                # Stream out JSON line immediately to disk
                out_f.write(json.dumps(store) + "\n")
                out_f.flush()

        browser.close()
        print(f"\n✅ Processing complete! Saved output to:\n'{output_file}'")


if __name__ == "__main__":
    INPUT_JSONL = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/coupons/stores_with_coupons.jsonl"
    OUTPUT_JSONL = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/coupons/stores_with_captured_links_2.jsonl"

    process_coupons_jsonl(input_file=INPUT_JSONL, output_file=OUTPUT_JSONL)