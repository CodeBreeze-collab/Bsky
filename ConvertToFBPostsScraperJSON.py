import json
import csv
import os


def convert_tsv_to_posts_scraper_json(file_path, output_path='posts_scraper_input.json'):
    """
    Converts TSV URLs into the specific JSON format for the Apify Facebook Posts Scraper.
    """
    start_urls = []

    if not os.path.exists(file_path):
        print(f"Error: The file '{file_path}' was not found.")
        return

    try:
        with open(file_path, mode='r', encoding='utf-8') as tsv_file:
            reader = csv.DictReader(tsv_file, delimiter='\t')

            for row in reader:
                url = row.get('URL')
                if url:
                    start_urls.append({"url": url.strip()})

        # This is the exact schema requested by the Facebook Posts Scraper
        posts_payload = {
            "captionText": True,  # Set to True so you can see the content of the posts
            "onlyPostsNewerThan": "30 days",  # Expanded to 30 days to catch more foster pleas
            "resultsLimit": 20,  # Scrapes the 20 most recent posts per page/group
            "startUrls": start_urls
        }

        with open(output_path, mode='w', encoding='utf-8') as json_file:
            json.dump(posts_payload, json_file, indent=4)

        print(f"Success! Processed {len(start_urls)} URLs.")
        print(f"Generated input file for Posts Scraper: {output_path}")

    except Exception as e:
        print(f"An unexpected error occurred: {e}")


if __name__ == "__main__":
    # --- CONFIGURATION ---
    # Ensure this matches the name of your .tsv file
    PATH_TO_TSV = "/Users/hdon/Downloads/ny_animal_rescues_and_groups.tsv"
    # ---------------------

    convert_tsv_to_posts_scraper_json(PATH_TO_TSV)