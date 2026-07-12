import os
import json
from datetime import datetime

# Read from your corrected dataset path
INPUT_DIR = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/needs_help_v2_/v3_corrected/video_enriched_5"
# Output to a new version directory
OUTPUT_DIR = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/needs_help_v2_/v3_corrected/video_enriched_5/with_urls/"


def parse_date_dir(dirname):
    try:
        return datetime.strptime(dirname, "%m-%d-%Y")
    except ValueError:
        return None


def get_sorted_date_dirs(input_dir):
    dirs = []
    if not os.path.exists(input_dir):
        return dirs
    for name in os.listdir(input_dir):
        path = os.path.join(input_dir, name)
        if os.path.isdir(path):
            dt = parse_date_dir(name)
            if dt:
                dirs.append((dt, path))
    dirs.sort(key=lambda x: x[0], reverse=True)
    return dirs


def collect_text(obj):
    """Recursively collect all human-readable text fields."""
    texts = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str):
                texts.append(v)
            else:
                texts.extend(collect_text(v))
    elif isinstance(obj, list):
        for item in obj:
            texts.extend(collect_text(item))
    return texts


def check_for_pledges(text):
    """
    Returns True if the text contains 'pledge', '$', or 'dollar'.
    'pledge' matches 'pledges', 'pledged', etc. due to substring matching.
    """
    text_lower = text.lower()
    return "pledge" in text_lower or "$" in text_lower or "dollar" in text_lower


def extract_urls_from_record(obj):
    """
    Extracts all full target destination URLs from standard Bluesky post structures.
    Safely inspects both raw Firehose event payloads and fully hydrated AppView structures.
    """
    found_urls = []

    def add_unique(url_str):
        if url_str and isinstance(url_str, str) and url_str not in found_urls:
            found_urls.append(url_str)

    # Compile possible locations for rich elements (top-level or nested inside an inner record object)
    evaluation_targets = [obj]
    if isinstance(obj, dict) and isinstance(obj.get("record"), dict):
        evaluation_targets.append(obj["record"])

    for target in evaluation_targets:
        # 1. Parse inline Rich Text Facet links (e.g., hidden links behind text anchors)
        facets = target.get("facets", [])
        if isinstance(facets, list):
            for facet in facets:
                if isinstance(facet, dict):
                    for feature in facet.get("features", []):
                        if isinstance(feature, dict) and feature.get("$type") == "app.bsky.richtext.facet#link":
                            add_unique(feature.get("uri"))

        # 2. Parse external link preview attachment cards
        embed = target.get("embed", {})
        if isinstance(embed, dict):
            embed_type = embed.get("$type", "")

            # Check for standard direct external attachment blocks
            if "app.bsky.embed.external" in embed_type:
                external_data = embed.get("external", {})
                if isinstance(external_data, dict):
                    add_unique(external_data.get("uri"))

            # Check for nested items combined alongside other media options
            elif "app.bsky.embed.recordWithMedia" in embed_type:
                media_block = embed.get("media", {})
                if isinstance(media_block, dict) and "app.bsky.embed.external" in media_block.get("$type", ""):
                    external_data = media_block.get("external", {})
                    if isinstance(external_data, dict):
                        add_unique(external_data.get("uri"))

    return found_urls


def process_file(input_file, output_file):
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    processed = 0
    pledge_count = 0

    with open(input_file, "r", encoding="utf-8") as infile, \
            open(output_file, "w", encoding="utf-8") as outfile:

        for line in infile:
            if not line.strip():
                continue

            record = json.loads(line)

            # Flatten all textual fields to make sure we don't miss text hidden in associated_posts
            combined_text = "\n".join(collect_text(record))

            # Run the boolean parameter evaluation
            has_pledge = check_for_pledges(combined_text)
            record["has_pledge"] = has_pledge

            # Extract full un-truncated destination links and assign them to the new array
            record["internal_urls"] = extract_urls_from_record(record)

            if has_pledge:
                pledge_count += 1

            outfile.write(json.dumps(record, ensure_ascii=False) + "\n")
            processed += 1

    print(f"   Done: processed={processed}, found {pledge_count} posts with pledges.")


def main():
    date_dirs = get_sorted_date_dirs(INPUT_DIR)
    if not date_dirs:
        print(f"No date directories found in {INPUT_DIR}")
        return

    for dt, date_dir in date_dirs:
        print(f"\nProcessing date directory: {dt.strftime('%m-%d-%Y')}")

        for root, _, files in os.walk(date_dir):
            for filename in files:
                if filename != "animal_centric_posts-w-loc-2.jsonl":
                    continue

                input_file = os.path.join(root, filename)
                relative = os.path.relpath(root, INPUT_DIR)
                output_file = os.path.join(OUTPUT_DIR, relative, filename)

                print(f"   {input_file}")
                process_file(input_file, output_file)


if __name__ == "__main__":
    main()