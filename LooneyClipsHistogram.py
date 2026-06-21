import os
import json
import matplotlib.pyplot as plt
from collections import Counter

# --- CONFIGURATION ---
ANALYSIS_DIR = '/Users/hdon/Projects/Tarot/looney_moon/tarot_hateful_spiteful_content/analysis/'
OUTPUT_IMAGE = 'analysis_histogram.png'


def main():
    if not os.path.exists(ANALYSIS_DIR):
        print(f"❌ Error: Directory not found: {ANALYSIS_DIR}")
        return

    all_tags = []

    # 1. Gather all .json files
    json_files = [f for f in os.listdir(ANALYSIS_DIR) if f.endswith('.json')]
    total_unique_videos = len(json_files)

    for filename in json_files:
        file_path = os.path.join(ANALYSIS_DIR, filename)
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
                for segment in data:
                    tags = segment.get('matches', [])
                    all_tags.extend(tags)
        except Exception as e:
            print(f"Could not process {filename}: {e}")

    if not all_tags:
        print(f"Processed {total_unique_videos} files, but found no matches.")
        return

    # 2. Count and Sort
    tag_counts = Counter(all_tags)
    sorted_items = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)
    labels, values = zip(*sorted_items)

    # 3. Create the Plot
    fig, ax = plt.subplots(figsize=(12, 7))
    bars = ax.bar(labels, values, color='#34495e', edgecolor='black', alpha=0.8)

    # 4. Annotations
    ax.bar_label(bars, padding=3, fontsize=11, fontweight='bold')

    # 5. Styling & Info Box
    ax.set_title('Frequency of Content Categories', fontsize=16, pad=25)
    ax.set_ylabel('Total Count', fontsize=12)

    # Add a text box in the top right with the unique video count
    stats_text = f"Total Unique Videos: {total_unique_videos}\nTotal Matches Found: {len(all_tags)}"
    ax.text(0.95, 0.95, stats_text, transform=ax.transAxes, fontsize=10,
            verticalalignment='top', horizontalalignment='right',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()

    # 6. Save result
    plt.savefig(OUTPUT_IMAGE)

    # Final Console Output
    print("-" * 30)
    print(f"ANALYSIS COMPLETE")
    print("-" * 30)
    print(f"Unique Videos Scanned: {total_unique_videos}")
    print(f"Total Matches Found:   {len(all_tags)}")
    print("-" * 30)
    for label, count in sorted_items:
        print(f"{label:20}: {count}")
    print("-" * 30)
    print(f"Histogram saved to: {OUTPUT_IMAGE}")


if __name__ == "__main__":
    main()