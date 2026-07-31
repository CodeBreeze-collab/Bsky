import requests
import csv
import sys


def save_bluesky_follows_to_tsv(actor_handle, output_filename=None):
    """
    Fetches the accounts a given Bluesky account is following
    and saves their Handle, DID, and Display Name to a .tsv file.
    """
    if not output_filename:
        # Dynamically names the file based on the handle being searched
        output_filename = f"{actor_handle}_following.tsv"

    url = "https://public.api.bsky.app/xrpc/app.bsky.graph.getFollows"
    params = {"actor": actor_handle, "limit": 100}

    print(f"Fetching accounts followed by @{actor_handle}...")

    try:
        # Open file with utf-8 encoding to preserve emojis and special characters
        with open(output_filename, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f, delimiter='\t')

            # Write column headers
            writer.writerow(["Handle", "DID", "Display Name"])

            total_count = 0
            while True:
                response = requests.get(url, params=params)
                if response.status_code != 200:
                    print(f"Error: Received status code {response.status_code} - {response.text}")
                    break

                data = response.json()
                follows = data.get("follows", [])

                if not follows:
                    break

                for account in follows:
                    handle = account.get("handle", "")
                    did = account.get("did", "")
                    display_name = account.get("displayName", "")

                    # Write row to TSV
                    writer.writerow([handle, did, display_name])
                    total_count += 1

                # Handle pagination via cursor
                cursor = data.get("cursor")
                if not cursor:
                    break
                params["cursor"] = cursor

        print(f"Successfully saved {total_count} rows to '{output_filename}'.")

    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    # Allows passing a handle via terminal argument (defaults to 'bsky.app' if left blank)
    target = "newyorktopnews.bsky.social"
    save_bluesky_follows_to_tsv(target)