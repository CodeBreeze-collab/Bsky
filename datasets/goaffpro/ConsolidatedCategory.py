import json
import os


def clean_categories(input_file, output_file):
    print(f"Reading from: {input_file}")
    print(f"Writing to: {output_file}")

    processed_count = 0

    with open(input_file, 'r', encoding='utf-8') as infile, open(output_file, 'w', encoding='utf-8') as outfile:
        for line in infile:
            if not line.strip():
                continue

            data = json.loads(line)

            # Remove the old 'category' field
            if "category" in data:
                del data["category"]

            # Rename 'consolidated_category' to 'category'
            if "consolidated_category" in data:
                data["category"] = data.pop("consolidated_category")
            else:
                # Fallback just in case a row missed the consolidation step
                data["category"] = "Uncategorized"

            # Write the cleaned JSON object to the new file
            outfile.write(json.dumps(data) + '\n')
            processed_count += 1

    print(f"Successfully processed {processed_count} stores.")


if __name__ == "__main__":
    # Your input path
    input_path = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/goaffpro/stores-consolidated-categories.jsonl"

    # New output path for the finalized data
    output_path = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/goaffpro/stores-final-categories.jsonl"

    if not os.path.exists(input_path):
        print(f"Error: Input file not found at {input_path}")
    else:
        clean_categories(input_path, output_path)