import json
import argparse
import os


def generate_animal_centric_jsonl(input_json_path, output_jsonl_path):
    # 1. Define the Allowed Enum Set
    VALID_STATUSES = {
        "Needs Foster",
        "Needs Home",
        "Needs Rescue",
        "Safe - With Foster",
        "Safe - With Rescue",
        "Safe - Adopted",
        "Euthanized"
    }

    if not os.path.exists(input_json_path):
        print(f"[!] Error: Input file not found at {input_json_path}")
        return

    with open(input_json_path, 'r', encoding='utf-8') as f:
        animals_list = json.load(f)

    print(f"📖 Processing {len(animals_list)} profiles from Step 2...")

    with open(output_jsonl_path, 'w', encoding='utf-8') as f_out:
        for animal in animals_list:
            # Access the first post for metadata
            post_details = animal.get('post_details', [])
            primary_post = post_details[0] if post_details else {}

            # 2. Extract and Validate Status
            raw_status = animal.get("status", "").strip()
            final_status = raw_status

            # 3. Build the flat record
            flat_record = {
                "animal_id": animal.get("animal_id"),
                "animal_name": animal.get("name"),
                "animal_species": animal.get("species"),
                "final_status": final_status,
                "final_description": animal.get("final_description"),
                "status_rationale": animal.get("status_rationale"),

                # Metadata for API/Frontend
                "city": primary_post.get("city", ""),
                "state": primary_post.get("state", ""),
                "country": primary_post.get("country", "USA"),
                "author_handle": primary_post.get("author_handle", ""),
                "indexedAt": primary_post.get("indexedAt", ""),
                "post_url": primary_post.get("post_url", ""),

                # Full history
                "associated_posts": [
                    {
                        "post_url": p.get("post_url"),
                        "text": p.get("text"),
                        "image_urls": p.get("image_urls", []),
                        "posted_at": p.get("posted_at")
                    } for p in post_details
                ]
            }

            # 4. Write as JSONL
            f_out.write(json.dumps(flat_record) + '\n')


# Run the process
if __name__ == "__main__":
    default_dir = '/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/needs_help/06-08-2026/'

    parser = argparse.ArgumentParser(description="Generate Animal Centric Flat JSONL Dataset")
    parser.add_argument("--input-file", type=str, default=os.path.join(default_dir, "aggregated_rescue_profiles.json"),
                        help="Path to input aggregated JSON file")
    parser.add_argument("--output-file", type=str,
                        default=os.path.join(default_dir, "animal_centric_posts-w-loc-2.jsonl"),
                        help="Path to output animal-centric JSONL file")

    args = parser.parse_args()

    generate_animal_centric_jsonl(args.input_file, args.output_file)
    print(f"✅ Successfully processed flat JSONL to: {args.output_file}")