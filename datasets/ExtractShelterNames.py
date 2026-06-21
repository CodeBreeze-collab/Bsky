import json


def get_shelter_profile_urls(file_path):
    # Using a set to automatically handle duplicates
    profile_urls = set()

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue

                data = json.loads(line)

                # Extract the username from the result object
                username = data.get('result', {}).get('ownerUsername')

                if username:
                    # Construct the full Instagram profile URL
                    url = f"https://www.instagram.com/{username}/"
                    profile_urls.add(url)

        # Print the final unique set
        print(f"--- Found {len(profile_urls)} Unique Shelters ---")
        for url in sorted(profile_urls):
            print(url)

    except FileNotFoundError:
        print(f"Error: The file '{file_path}' was not found.")


# Run the function
get_shelter_profile_urls('instagram_post_results.jsonl')