import json

# Replace with your actual filename
input_file = '/Users/hdon/Downloads/dataset_crawler-google-places_2026-03-13_19-19-50-488.json'
output_file = '/Users/hdon/Desktop/apify_input-new-york.json'


def prepare_apify_input(file_path):
    profile_names = []

    with open(file_path, 'r', encoding='utf-8') as f:
        try:
            # Load the entire file as a standard JSON list
            data_list = json.load(f)

            # If the JSON is a list of objects
            if isinstance(data_list, list):
                for item in data_list:
                    if "title" in item:
                        profile_names.append(item["title"])
            # In case it's a single object (though unlikely here)
            elif isinstance(data_list, dict):
                if "title" in data_list:
                    profile_names.append(data_list["title"])

        except json.JSONDecodeError as e:
            print(f"Error parsing JSON: {e}")

    # Create the structured dictionary for the actor
    payload = {
        "profileNames": profile_names,
        "socials": [
            "facebook",
            "instagram",
            "twitter",
            "x",
            "threads",
            "tiktok",
            "youtube"
        ]
    }

    return payload


# Generate the payload
apify_payload = prepare_apify_input(input_file)

# Save it to a file you can copy-paste into Apify
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(apify_payload, f, indent=4)

print(f"Success! {len(apify_payload['profileNames'])} rescues processed.")
print(f"Input file for Apify saved as: {output_file}")