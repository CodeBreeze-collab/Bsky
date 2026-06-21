import json
import os


def normalize_status(status):
    """Clean up common LLM typographical quirks."""
    if not status:
        return ""
    # Replace En Dashes (\u2013) and Em Dashes (\u2014) with standard hyphens
    status = status.replace('\u2013', '-').replace('\u2014', '-')
    # Remove any extra whitespace and normalize casing
    return status.strip()


def map_jsonl_status(file_path):
    # Standardized target list
    status_mapping = {
        # --- Needs Foster ---
        "Urgent - At Risk - Medical Needs": "Needs Foster",
        "Urgent - At Risk": "Needs Foster",
        "Urgent Foster Needed": "Needs Foster",
        "Urgent Foster/Adoption Required": "Needs Foster",

        # --- Needs Home ---
        "Available for Adoption": "Needs Home",
        "Available for Adoption (Medical Needs)": "Needs Home",

        # Add the rest of your 7 allowed statuses here...
    }

    temp_output = []
    modified = False

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line: continue

                data = json.loads(line)

                if "final_status" in data:
                    old_val = data["final_status"]
                    # Normalize the incoming value before checking the map
                    clean_val = normalize_status(old_val)

                    # Try to map the cleaned value, default to "Needs Home" if still unknown
                    new_val = status_mapping.get(clean_val, "Needs Home")

                    if old_val != new_val:
                        data["final_status"] = new_val
                        modified = True

                temp_output.append(json.dumps(data))

        if modified:
            with open(file_path, 'w', encoding='utf-8') as f:
                for entry in temp_output:
                    f.write(entry + '\n')
            print(f"Fixed & Standardized: {os.path.basename(file_path)}")

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    map_jsonl_status("/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/needs_help/04-02-2026/animal_centric_posts-w-loc-2-4-raw.jsonl")