import json

# Define file paths
categorized_file = "/Users/hdon/Desktop/go-affpro-pages/store_classifications/categorized_stores_3.jsonl"
target_file = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/goaffpro/enriched_stores-w-products-filtered-final.jsonl"
output_file = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/goaffpro/enriched_stores-w-products-filtered-final-categorized.jsonl"


def normalize_url(url):
    """Ensure the URL has a consistent scheme for matching."""
    url = url.strip().lower()
    if not url.startswith("http://") and not url.startswith("https://"):
        return f"https://{url}"
    return url


print("Loading and normalizing categories...")
store_categories = {}

# Step 1: Read and index the categorized stores
with open(categorized_file, "r", encoding="utf-8") as f:
    for line in f:
        if line.strip():
            try:
                data = json.loads(line)
                raw_url = data.get("url", "")
                if raw_url:
                    norm_url = normalize_url(raw_url)
                    store_categories[norm_url] = {
                        "category": data.get("category"),
                        "reasoning": data.get("reasoning")
                    }
            except json.JSONDecodeError as e:
                print(f"Skipping invalid JSON line: {e}")

print(f"Loaded {len(store_categories)} unique categorized stores.")

print("Enriching target dataset...")
total_count = 0
enriched_count = 0

# Step 2: Read target file, enrich records, and write to output file
with open(target_file, "r", encoding="utf-8") as fin, open(output_file, "w", encoding="utf-8") as fout:
    for line in fin:
        if line.strip():
            total_count += 1
            try:
                record = json.loads(line)
                base_url = normalize_url(record.get("baseUrl", ""))

                # Check if the normalized base URL exists in our dictionary
                if base_url in store_categories:
                    record["category"] = store_categories[base_url]["category"]
                    record["reasoning"] = store_categories[base_url]["reasoning"]
                    enriched_count += 1
                else:
                    # Optional fallback if no category is found
                    record["category"] = None
                    record["reasoning"] = None

                fout.write(json.dumps(record) + "\n")
            except json.JSONDecodeError as e:
                print(f"Skipping invalid JSON line in target file: {e}")

print("\n--- Enrichment Complete ---")
print(f"Total records processed: {total_count}")
print(f"Successfully matched & enriched: {enriched_count}")
print(f"Output saved to: {output_file}")