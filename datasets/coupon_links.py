import time
from playwright.sync_api import sync_playwright


def get_final_coupon_destination(url: str):
    with sync_playwright() as p:
        # Launch Chromium with popup blocking disabled
        browser = p.chromium.launch(
            headless=False,
            args=["--disable-popup-blocking", "--start-maximized"],
        )

        context = browser.new_context(
            no_viewport=True, permissions=["clipboard-read", "clipboard-write"]
        )

        # Track network calls to log outbound affiliate tracking links
        outbound_requests = []

        def track_requests(req):
            if any(
                keyword in req.url.lower()
                for keyword in ["/out/", "redirect", "affiliate", "click"]
            ):
                outbound_requests.append(req.url)

        context.on("request", track_requests)

        page = context.new_page()

        print(f"🌐 Step 1: Navigating to {url}")
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        # 1. Click primary "Show code" button on main page
        initial_button = page.locator(
            "button:has-text('Show code'), a:has-text('Show code')"
        ).first

        print("🖱️ Clicking primary 'Show code' button...")
        with context.expect_page(timeout=10000) as deal_tab_info:
            initial_button.click(no_wait_after=True)

        deal_tab = deal_tab_info.value
        deal_tab.wait_for_load_state("domcontentloaded")
        print(f"📍 Step 1 Complete! Deal Tab URL -> {deal_tab.url}\n")

        deal_tab.wait_for_timeout(2000)

        # 2. Locate and click secondary [Copy Code] button inside the deal modal
        copy_button = deal_tab.locator(
            "button:has-text('Copy'), a:has-text('Copy')"
        ).first

        if copy_button.count() > 0:
            print("🖱️ Step 2: Clicking [Copy Code] button...")

            try:
                # Expect popup tab triggered directly by the Copy button click
                with deal_tab.expect_popup(timeout=10000) as popup_info:
                    copy_button.click()

                final_tab = popup_info.value
                final_tab.wait_for_load_state("domcontentloaded", timeout=10000)

                print(
                    f"\n🎉 SUCCESS! Final Merchant Destination URL ->"
                    f" {final_tab.url}"
                )

            except Exception as e:
                print(f"⚠️ Popup event timeout: {e}")
                print(f"Current Tab URL: {deal_tab.url}")
        else:
            print("❌ Could not locate [Copy Code] button on deal tab.")

        print("\n--- Outbound/Affiliate Requests Caught ---")
        if outbound_requests:
            for req_url in set(outbound_requests):
                print(f"🔗 {req_url}")
        else:
            print("No outbound redirect requests logged.")

        print("\nPausing 3s before closing...")
        time.sleep(3)
        browser.close()


if __name__ == "__main__":
    test_url = "https://www.goodsearch.com/coupons/1800petmeds.com"
    get_final_coupon_destination(test_url)