import pandas as pd
import json
import os


def aggregate_to_jsonl(file_paths, output_filename="unique_accounts.jsonl"):
    """
    Reads multiple CSVs, cleans the data, and writes a unique
    JSONL file containing handle, display name, description, and DID.
    """
    # Use a dictionary to track unique DIDs and keep the associated profile data
    unique_accounts = {}

    print(f"Processing {len(file_paths)} files...")

    for path in file_paths:
        if not os.path.exists(path):
            print(f"Warning: File not found at {path}, skipping.")
            continue

        try:
            # Using python engine and skipping bad lines to avoid crashes
            df = pd.read_csv(
                path,
                engine='python',
                on_bad_lines='skip'
            )

            # Iterate through rows and store by DID to ensure uniqueness
            for _, row in df.iterrows():
                did = row.get("DID")
                if did and pd.notna(did):
                    unique_accounts[did] = {
                        "handle": row.get("Handle", ""),
                        "displayName": row.get("Display Name", ""),
                        "description": row.get("Bio", ""),
                        "did": did
                    }
            print(f"Successfully processed: {os.path.basename(path)}")

        except Exception as e:
            print(f"Could not read {path} due to error: {e}")

    # Write to JSONL file
    with open(output_filename, "w", encoding="utf-8") as f:
        for account in unique_accounts.values():
            f.write(json.dumps(account) + "\n")

    print(f"\nDone! Found {len(unique_accounts)} unique accounts.")
    print(f"JSONL file saved to '{output_filename}'.")


if __name__ == "__main__":
    # Add your file paths here
    my_csv_files = [
        "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/v2/profile_audits/blocked_accounts_details-newenglandtopnews.csv",
        "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/v2/profile_audits/blocked_accounts_details-vegansearchengine.csv"
    ]

    aggregate_to_jsonl(my_csv_files)