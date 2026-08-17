import json
from pathlib import Path
import requests


def enrich_stores_with_products(
    input_jsonl_path: str,
    output_jsonl_path: str = 'enriched_stores.jsonl',
    max_products_per_store: int = 10,
):
  """Reads a JSONL file of store URLs, queries Shopify's /products.json endpoint,

  writes out each record in real-time, and supports safe resume/restarting by
  checking already processed stores in the output file.
  """
  input_path = Path(input_jsonl_path)
  if not input_path.exists():
    print(f'Error: File "{input_jsonl_path}" not found.')
    return

  output_path = input_path.parent / output_jsonl_path

  # 1. Restart-proof: Load already processed store IDs from output file if it exists
  processed_store_ids = set()
  success_count = 0

  if output_path.exists():
    print(f'Found existing output file. Loading progress for resume...')
    with open(output_path, 'r', encoding='utf-8') as out_f:
      for line in out_f:
        if line.strip():
          try:
            record = json.loads(line)
            store_id = record.get('store_id')
            if store_id:
              processed_store_ids.add(str(store_id))
              if record.get('product_urls'):
                success_count += 1
          except json.JSONDecodeError:
            continue
    print(
        f'Resuming: Found {len(processed_store_ids)} already processed stores.'
    )

  headers = {
      'User-Agent': (
          'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
          'AppleWebKit/537.36 (KHTML, like Gecko) '
          'Chrome/120.0.0.0 Safari/537.36'
      )
  }

  # 2. Open output file in append mode ('a') for real-time writing
  with open(output_path, 'a', encoding='utf-8') as out_f:
    with open(input_path, 'r', encoding='utf-8') as in_f:
      for line in in_f:
        if not line.strip():
          continue
        record = json.loads(line)
        store_id = record.get('store_id')
        store_url = record.get('store_url', '').strip()

        # Skip if already processed (Restart-proof check)
        if store_id and str(store_id) in processed_store_ids:
          print(
              f'Skipping already processed store ID: {store_id} ({store_url})'
          )
          continue

        # Normalize store URL to include protocol
        if not store_url.startswith(('http://', 'https://')):
          base_url = f'https://{store_url}'
        else:
          base_url = store_url

        product_urls = []

        # Query Shopify's public products.json endpoint
        shopify_api_url = f'{base_url.rstrip("/")}/products.json?limit={max_products_per_store}'
        try:
          response = requests.get(
              shopify_api_url, headers=headers, timeout=10, allow_redirects=True
          )
          if response.status_code == 200:
            data = response.json()
            products = data.get('products', [])
            for prod in products:
              handle = prod.get('handle')
              if handle:
                product_url = f'{base_url.rstrip("/")}/products/{handle}'
                product_urls.append(product_url)
            if product_urls:
              success_count += 1
        except Exception:
          # Store might not be Shopify or request timed out/failed
          pass

        # Add the extracted product URLs to the record dictionary
        record['product_urls'] = product_urls

        # 3. Write out in real-time immediately to disk
        out_f.write(json.dumps(record) + '\n')
        out_f.flush()  # Force write to disk instantly

        # Track as processed in memory
        if store_id:
          processed_store_ids.add(str(store_id))

        print(
            f'Processed & Saved: {store_url} | Products found:'
            f' {len(product_urls)}'
        )

  print(
      f'\nProcessing complete. Successfully enriched stores with products:'
      f' {success_count}. Saved to: {output_path.absolute()}'
  )


if __name__ == '__main__':
  input_jsonl = '/Users/hdon/Desktop/go-affpro-pages/goaffpro-my-stores/extracted_my_stores_2.jsonl'
  enrich_stores_with_products(input_jsonl, 'enriched_stores.jsonl')