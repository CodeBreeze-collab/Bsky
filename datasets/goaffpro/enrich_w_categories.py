import json
from urllib.parse import urlparse


class StoreCategoryEnricher:

  def __init__(self, categories_path, target_path, output_path):
    self.categories_path = categories_path
    self.target_path = target_path
    self.output_path = output_path

  def _normalize_to_domain(self, url_str):
    """Extracts a clean lowercase domain key (e.g., 'akmountaindog.com')

    from raw URLs or domain strings for robust cross-matching.
    """
    if not url_str:
      return None
    clean = url_str.strip()

    # Skip strings that are clearly company names rather than domains/URLs
    if " " in clean and not clean.startswith(("http://", "https://")):
      return None

    if not clean.startswith(("http://", "https://")):
      clean = "https://" + clean

    try:
      parsed = urlparse(clean)
      hostname = (parsed.hostname or "").lower()
      if hostname.startswith("www."):
        hostname = hostname[4:]
      return hostname if hostname else None
    except Exception:
      return None

  def load_categories(self):
    """Reads the category .jsonl file and builds a lookup map indexed by clean domain key."""
    category_map = {}
    loaded_count = 0

    try:
      with open(self.categories_path, "r", encoding="utf-8") as f:
        for line in f:
          line = line.strip()
          if not line:
            continue
          try:
            data = json.loads(line)
            raw_url = data.get("url")
            category = data.get("category", "Unknown")

            domain_key = self._normalize_to_domain(raw_url)
            if domain_key:
              category_map[domain_key] = category
              loaded_count += 1
          except json.JSONDecodeError:
            continue
      print(f"Loaded {loaded_count} valid categories into lookup map.")
    except FileNotFoundError:
      print(f"Error: Categories file not found at '{self.categories_path}'")

    return category_map

  def enrich(self):
    """Reads target stores, matches with category map via normalized domain, and writes enriched output."""
    category_map = self.load_categories()
    processed = 0
    enriched = 0
    skipped = 0

    with open(self.target_path, "r", encoding="utf-8") as infile, open(
        self.output_path, "w", encoding="utf-8"
    ) as outfile:
      for line in infile:
        line = line.strip()
        if not line:
          continue

        try:
          record = json.loads(line)
          base_url = record.get("baseUrl")
          domain_key = self._normalize_to_domain(base_url)

          # Match domain and assign category if found
          if domain_key and domain_key in category_map:
            record["category"] = category_map[domain_key]
            enriched += 1
          else:
            # Fallback if category doesn't already exist in the record
            if "category" not in record or not record["category"]:
              record["category"] = "Unknown"

          outfile.write(json.dumps(record) + "\n")
          processed += 1

        except json.JSONDecodeError:
          skipped += 1

    print(
        f"✨ Enrichment complete! Processed {processed} records | Enriched"
        f" {enriched} categories | Skipped {skipped} malformed lines."
    )


def main():
  # Hardcoded paths as specified
  categories_file = (
      "/Users/hdon/Desktop/go-affpro-pages/store_classifications/categorized_stores_3.jsonl"
  )
  target_stores_file = "clean_merchants.jsonl"  # Update to your target file path
  output_enriched_file = "enriched_stores.jsonl"

  print(f"Starting store category enrichment...")
  enricher = StoreCategoryEnricher(
      categories_file, target_stores_file, output_enriched_file
  )
  enricher.enrich()


if __name__ == "__main__":
  main()