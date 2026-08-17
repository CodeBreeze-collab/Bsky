import requests

url = "https://famousskincarefordogs.com/products.json?limit=250"
response = requests.get(url)

if response.status_code == 200:
    data = response.json()
    product_urls = []

    for product in data.get("products", []):
        handle = product.get("handle")
        product_url = f"https://famousskincarefordogs.com/products/{handle}"
        product_urls.append(product_url)

    print(f"Found {len(product_urls)} products:")
    for p_url in product_urls[:5]:  # Print first 5
        print(p_url)
else:
    print("Failed to fetch products.")