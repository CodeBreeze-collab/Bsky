import json

NEEDS_HELP_ = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/needs_help/"


def filter_jsonl(input_path, output_path):
    with open(input_path, "r", encoding="utf-8") as infile, \
            open(output_path, "w", encoding="utf-8") as outfile:

        for line_number, line in enumerate(infile, start=1):
            line = line.strip()
            if not line:
                continue  # skip empty lines

            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                print(f"Skipping invalid JSON on line {line_number}")
                continue

            # Apply filtering conditions
            image_urls = record.get("image_urls", [])
            city = record.get("city", "")
            state = record.get("state", "")

            if (
                    isinstance(image_urls, list) and len(image_urls) > 0
                    and isinstance(city, str) and city.strip()
                    and isinstance(state, str) and state.strip()
            ):
                outfile.write(json.dumps(record) + "\n")

    print("Filtering complete.")

# /Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/needs_help/03-13-2026/bluesky_rescue_posts_output-w-loc.jsonl
if __name__ == "__main__":
    input_file = "%s04-02-2026/bluesky_rescue_posts_output-w-loc.jsonl" % NEEDS_HELP_
    output_file = "%s04-02-2026/bluesky_rescue_posts_output-complete.jsonl" % NEEDS_HELP_
    filter_jsonl(input_file, output_file)