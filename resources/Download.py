from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()

    def handle_request(request):
        print(request.method, request.resource_type, request.url)

    page.on("request", handle_request)

    page.goto("https://luluvid.com/938bf227-30f8-4f48-a6a1-c7213684131d")

    page.wait_for_timeout(15000)

    browser.close()