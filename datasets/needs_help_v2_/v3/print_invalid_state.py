import os
import json

# Define your source and target directories
INPUT_DIR = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/needs_help_v2_/v3"
OUTPUT_DIR = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/needs_help_v2_/v3_corrected"

# Mapping dictionary for known incorrect states/countries
LOCATION_MAP = {
    # US States converted to 2-letter codes
    "Oregon": {"state": "OR", "country": "USA"},
    "California": {"state": "CA", "country": "USA"},
    "Maryland": {"state": "MD", "country": "USA"},
    "Minnesota": {"state": "MN", "country": "USA"},
    "Georgia": {"state": "GA", "country": "USA"},
    "Vermont": {"state": "VT", "country": "USA"},
    "Delaware": {"state": "DE", "country": "USA"},
    "South Carolina": {"state": "SC", "country": "USA"},

    # International corrections (fixing UK/Ireland/Canada locations mislabeled as USA)
    "Shropshire": {"state": "Shropshire", "country": "United Kingdom"},
    "England": {"state": "", "country": "United Kingdom"},
    "Wales": {"state": "", "country": "United Kingdom"},
    "Wales, England": {"state": "", "country": "United Kingdom"},
    "North Wales": {"state": "North Wales", "country": "United Kingdom"},
    "North Wales, Northwest England": {"state": "North Wales", "country": "United Kingdom"},
    "North Wales, North West England": {"state": "North Wales", "country": "United Kingdom"},
    "North Wales; North West England": {"state": "North Wales", "country": "United Kingdom"},
    "North Wales/Northwest England": {"state": "North Wales", "country": "United Kingdom"},
    "Cumbria": {"state": "Cumbria", "country": "United Kingdom"},
    "County Galway": {"state": "County Galway", "country": "Ireland"},
    "Galway": {"state": "County Galway", "country": "Ireland"},
    "Alberta": {"state": "AB", "country": "Canada"},

    # Non-single state regions (moved out of 'state' to 'other_region')
    "East Coast": {
        "state": "",
        "country": "USA",
        "other_region": "East Coast"
    },
    "East Coast states (NY, NJ, NH, NE, ME, MD, DC, DE, CT, PA, VA, RI, VT)": {
        "state": "",
        "country": "USA",
        "other_region": "East Coast"
    },
    "NY, NJ, NH, NE, ME, MD, DC, DE, CT, PA, VA, RI, VT": {
        "state": "",
        "country": "USA",
        "other_region": "East Coast / Mid-Atlantic & New England"
    }
}

# Walk through the source directory
for root, _, files in os.walk(INPUT_DIR):
    for filename in files:

        # Process only JSONL files
        if not filename.endswith(".jsonl"):
            continue

        # Optional: Uncomment the lines below if you want to restrict it to ONLY this specific filename
        # if filename != "animal_centric_posts-w-loc-2.jsonl":
        #     continue

        input_filepath = os.path.join(root, filename)

        # Recreate the exact subfolder structure in the target directory
        relative_path = os.path.relpath(root, INPUT_DIR)
        target_subfolder = os.path.join(OUTPUT_DIR, relative_path)
        os.makedirs(target_subfolder, exist_ok=True)
        output_filepath = os.path.join(target_subfolder, filename)

        with open(input_filepath, "r", encoding="utf-8") as f_in, \
                open(output_filepath, "w", encoding="utf-8") as f_out:

            for line in f_in:
                if not line.strip():
                    f_out.write(line)  # Maintain empty lines if any exist
                    continue

                record = json.loads(line)
                state_raw = record.get("state", "").strip()

                # If the raw state matches a key in our correction map
                if state_raw in LOCATION_MAP:
                    correction = LOCATION_MAP[state_raw]

                    # 1. Update Root Level Properties
                    record["state"] = correction.get("state", "")
                    record["country"] = correction.get("country", record.get("country"))

                    if "other_region" in correction:
                        record["other_region"] = correction["other_region"]
                    elif "other_region" in record:
                        # Ensure old data doesn't carry an obsolete region parameter
                        record.pop("other_region")

                    # 2. Update Nested 'extracted_location' Object Properties for Data Consistency
                    if "extracted_location" in record and isinstance(record["extracted_location"], dict):
                        ext_loc = record["extracted_location"]
                        ext_loc["state_or_region"] = correction.get("state", "")
                        ext_loc["country"] = correction.get("country", ext_loc.get("country"))

                        if "other_region" in correction:
                            ext_loc["other_region"] = correction["other_region"]
                        elif "other_region" in ext_loc:
                            ext_loc.pop("other_region")

                # Write the updated record to the new destination file
                # ensure_ascii=False preserves native emojis/special characters in post descriptions
                f_out.write(json.dumps(record, ensure_ascii=False) + "\n")

print(f"Data mapping complete! Corrected files saved to:\n{OUTPUT_DIR}")