import json
import os

# File paths
input_path = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/goaffpro/enriched_stores-w-products.jsonl"
output_path = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/goaffpro/filtered_enriched_stores.jsonl"


def filter_jsonl(input_file, output_file):
    processed_count = 0
    kept_count = 0

    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(input_file, 'r', encoding='utf-8') as infile, \
            open(output_file, 'w', encoding='utf-8') as outfile:

        for line_num, line in enumerate(infile, 1):
            line_stripped = line.strip()
            if not line_stripped:
                continue

            try:
                data = json.loads(line_stripped)
                processed_count += 1

                store_url = data.get("store_url", "")
                commission = data.get("commission")

                # Check conditions
                has_goaffpro = "https://goaffpro.com/" in store_url
                is_commission_null = (
                        commission is None
                        or str(commission).strip().lower() in ["null", "none", ""]
                )

                # Omit if store_url has goaffpro OR commission is null
                if has_goaffpro or is_commission_null:
                    continue

                # Otherwise, write the record to the output file
                outfile.write(json.dumps(data) + '\n')
                kept_count += 1

            except json.JSONDecodeError as e:
                print(f"Warning: Skipping invalid JSON on line {line_num}: {e}")

    print("--- Filtering Summary ---")
    print(f"Total lines processed: {processed_count}")
    print(f"Total lines kept: {kept_count}")
    print(f"Total lines omitted: {processed_count - kept_count}")
    print(f"Filtered file saved to: {output_file}")


if __name__ == "__main__":
    filter_jsonl(input_path, output_path)