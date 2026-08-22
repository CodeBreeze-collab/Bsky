import json
from collections import Counter


def generate_category_histogram(input_file):
    categories = []

    # Read the JSONL file and extract categories
    with open(input_file, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                category = data.get("category")
                if category:
                    categories.append(category.strip())
                else:
                    categories.append("Uncategorized")
            except json.JSONDecodeError:
                continue

    # Count occurrences of each category
    counts = Counter(categories)
    sorted_counts = counts.most_common()  # Sort highest to lowest

    if not sorted_counts:
        print("No categories found in the file.")
        return

    print(f"\n--- Store Category Histogram (Total Stores: {len(categories)}) ---\n")

    # Formatting variables for a neat text chart
    max_count = sorted_counts[0][1]
    max_bar_width = 40  # Maximum width of the text bar

    for category, count in sorted_counts:
        # Calculate scaled bar size
        bar_length = int((count / max_count) * max_bar_width) if max_count > 0 else 0
        bar = "#" * bar_length

        # Print aligned row: Category Name | Count | Bar Chart
        print(f"{category:<30} | {count:>5}  {bar}")

    print("\n" + "-" * 60)


if __name__ == "__main__":
    # Pointing to your summary-enriched file (or you can use your other dataset file)

    input_path = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/goaffpro/stores-consolidated-categories-aff-network-final-fixed.jsonl"
    generate_category_histogram(input_path)