import json
import time
import requests


def fetch_bluesky_media(input_file="/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/v2/adult.jsonl", output_file="adult_media_urls.jsonl"):
    base_url = "https://api.bsky.app/xrpc/app.bsky.actor.getProfile"

    print(f"Reading DIDs from {input_file} and fetching media URLs...")

    with open(input_file, "r", encoding="utf-8") as infile, open(output_file, "w", encoding="utf-8") as outfile:
        for line in infile:
            if not line.strip():
                continue

            try:
                data = json.loads(line)
                did = data.get("did")
                handle = data.get("handle")

                if not did:
                    print(f"Skipping line: No DID found for handle {handle}")
                    continue

                # Query the Bluesky public API
                response = requests.get(base_url, params={"actor": did})

                if response.status_code == 200:
                    profile_info = response.json()

                    # Extract thumbnail (avatar) and banner URLs
                    avatar_url = profile_info.get("avatar")
                    banner_url = profile_info.get("banner")

                    # Store the results
                    result = {
                        "handle": handle,
                        "did": did,
                        "thumbnail_url": avatar_url,
                        "banner_url": banner_url
                    }

                    outfile.write(json.dumps(result) + "\n")
                    print(f"Successfully processed: {handle}")

                elif response.status_code == 429:
                    print("Rate limit reached. Sleeping for 5 seconds...")
                    time.sleep(5)
                else:
                    print(f"Failed to fetch profile for {handle} (Status Code: {response.status_code})")

            except Exception as e:
                print(f"Error processing record: {e}")

            # Polite rate limiting delay between requests
            time.sleep(0.2)


if __name__ == "__main__":
    fetch_bluesky_media()