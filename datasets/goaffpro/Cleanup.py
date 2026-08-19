import json
from urllib.parse import urlparse


def normalize_url(url_str):
  if not url_str:
    return None
  clean = url_str.strip()
  # Prepend https:// if missing
  if not clean.startswith(("http://", "https://")):
    clean = "https://" + clean
  try:
    parsed = urlparse(clean)
    # Keep path if present (e.g., for specific product landing pages)
    path = parsed.path if parsed.path and parsed.path != "/" else ""
    return f"{parsed.scheme}://{parsed.netloc}{path}"
  except Exception:
    return None


def extract_name_from_url(url):
  try:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").replace("www.", "")
    domain_part = hostname.split(".")[0]
    return domain_part.capitalize()
  except Exception:
    return "Merchant"


def clean_jsonl_file(input_filename, output_filename):
  processed = 0
  skipped = 0

  with open(input_filename, "r", encoding="utf-8") as infile, open(
      output_filename, "w", encoding="utf-8"
  ) as outfile:
    for line in infile:
      line = line.strip()
      if not line:
        continue

      try:
        data = json.loads(line)

        # 1. Handle URL mapping & normalization
        raw_url = data.get("store_url") or data.get("baseUrl") or data.get("url")
        base_url = normalize_url(raw_url)

        if not base_url:
          skipped += 1
          continue

        # 2. Handle ID and Name mapping
        merchant_id = str(data.get("store_id") or data.get("merchantId") or "")
        name = data.get("name") or extract_name_from_url(base_url)

        # 3. Construct the standardized record
        clean_record = {
            "baseUrl": base_url,
            "merchantId": merchant_id,
            "name": name,
        }

        # 4. Preserve valuable context data if present
        for optional_field in [
            "commission",
            "source_file",
            "product_urls",
            "category",
            "description",
        ]:
          if optional_field in data:
            clean_record[optional_field] = data[optional_field]

        outfile.write(json.dumps(clean_record) + "\n")
        processed += 1

      except json.JSONDecodeError:
        skipped += 1
        print("Warning: Skipped malformed JSON line.")

  print(f"✨ Complete! Cleaned {processed} records (Skipped {skipped}).")


def main():
  # Hardcoded file paths (change these values as needed)
  input_filename = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/goaffpro/enriched_stores-w-products-filtered.jsonl"
  output_filename = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/goaffpro/enriched_stores-w-products-cleaned.jsonl"

  print(f"Processing '{input_filename}' -> '{output_filename}'...")
  clean_jsonl_file(input_filename, output_filename)


if __name__ == "__main__":
  main()