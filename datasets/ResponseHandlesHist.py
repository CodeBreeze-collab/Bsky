import json
import sys
import os
from collections import Counter
import matplotlib.pyplot as plt


def analyze_handle_frequency(file_path):
    """Reads a JSONL file and plots a histogram of handle occurrences."""
    handle_counts = Counter()

    # Verify file exists
    if not os.path.exists(file_path):
        print(f"Error: The file '{file_path}' does not exist.")
        return

    # 1. Process the file line-by-line
    with open(file_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                handles = data.get('handles', [])
                handle_counts.update(handles)
            except json.JSONDecodeError:
                print(f"Skipping malformed JSON on line {line_num}")

    if not handle_counts:
        print("No data found to plot.")
        return

    # 2. Prepare data for plotting (Top 20 most frequent)
    most_common = handle_counts.most_common(20)
    names, counts = zip(*most_common)

    # 3. Visualization
    plt.figure(figsize=(12, 7))
    bars = plt.bar(names, counts, color='#3b82f6', edgecolor='#1d4ed8')

    # Add count labels on top of each bar
    for bar in bars:
        yval = bar.get_height()
        plt.text(bar.get_x() + bar.get_width() / 2, yval + 0.1, yval, ha='center', va='bottom')

    plt.xlabel('Handles', fontweight='bold')
    plt.ylabel('Frequency (Number of Posts)', fontweight='bold')
    plt.title('Top 20 Most Frequent Handles', fontsize=14, pad=20)
    plt.xticks(rotation=45, ha='right')

    plt.tight_layout()
    plt.show()


def main():
    """Main entry point of the script."""
    # You can change this string to your filename,
    # or even use sys.argv[1] to pass it via command line
    target_file = '/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/bluesky_post_interactions.jsonl'

    print(f"--- Starting Analysis on {target_file} ---")
    analyze_handle_frequency(target_file)
    print("--- Analysis Complete ---")


if __name__ == "__main__":
    main()