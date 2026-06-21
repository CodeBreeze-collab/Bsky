import json
import csv
import os


def convert_tsv_to_apify_json(file_path, output_path='apify_input.json'):
    """
    Reads a TSV file and converts the 'URL' column into Apify's startUrls JSON format.
    """
    start_urls = []

    if not os.path.exists(file_path):
        print(f"Error: The file '{file_path}' does not exist.")
        return

    try:
        with open(file_path, mode='r', encoding='utf-8') as tsv_file:
            # Using DictReader handles the header row automatically
            reader = csv.DictReader(tsv_file, delimiter='\t')

            for row in reader:
                # Ensure we are grabbing the 'URL' column
                url = row.get('URL')
                if url:
                    start_urls.append({"url": url.strip()})

        # Build the final structure
        apify_payload = {"startUrls": start_urls}

        # Write to the JSON file
        with open(output_path, mode='w', encoding='utf-8') as json_file:
            json.dump(apify_payload, json_file, indent=4)

        print(f"Success! Processed {len(start_urls)} URLs.")
        print(f"JSON file generated: {output_path}")

    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    # --- CONFIGURATION ---
    # Update this path to point to your actual .tsv file
    PATH_TO_TSV = "/Users/hdon/Downloads/ny_animal_rescues_and_groups.tsv"
    # ---------------------

    convert_tsv_to_apify_json(PATH_TO_TSV)