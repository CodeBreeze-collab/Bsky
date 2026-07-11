import os
import json
import time
import pandas as pd
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

# Initialize Gemini Client
client = genai.Client()


# --- Structured Output Schema ---
class SafetyResult(BaseModel):
    did: str
    is_adult_content: bool
    explanation: str


class BatchSafetyResponse(BaseModel):
    results: list[SafetyResult]


def load_processed_dids(output_filename):
    """Reads the existing JSONL file to find already processed DIDs."""
    processed_dids = set()
    if os.path.exists(output_filename):
        with open(output_filename, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        data = json.loads(line)
                        processed_dids.add(data["did"])
                    except json.JSONDecodeError:
                        continue
    return processed_dids


def process_batch(batch_rows):
    """Sends a batch of accounts to Gemini using Structured Outputs."""
    # Format the batch into a readable string for the model
    accounts_input = []
    for r in batch_rows:
        accounts_input.append(f"DID: {r['did']}\nHandle: {r['handle']}\nBio: {r['description']}\n---")

    prompt = f"""
    Analyze the following Bluesky profiles for adult content.
    Provide a safety assessment for EVERY account listed below.

    Accounts to analyze:
    {chr(10).join(accounts_input)}
    """

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",  # Best model for fast, structured batch tasks
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=BatchSafetyResponse,
                temperature=0.1,  # Low temperature for more consistent classification
            ),
        )

        # Parse the automatically validated JSON response
        response_data = json.loads(response.text)
        # Create a mapping of DID -> Safety Info
        return {res["did"]: res for res in response_data.get("results", [])}

    except Exception as e:
        print(f"Error processing batch: {e}")
        # Return empty so the loop knows this batch failed (will retry on next run)
        return {}


def process_to_jsonl(file_paths, output_filename="audited_accounts.jsonl", batch_size=10):
    # 1. Restart Friendliness: Load what we've already done
    processed_dids = load_processed_dids(output_filename)
    if processed_dids:
        print(f"Found {len(processed_dids)} already processed accounts. Skipping them.")

    # 2. Gather all unique, unprocessed accounts across files
    pending_accounts = []
    seen_dids_this_run = set()

    for path in file_paths:
        if not os.path.exists(path):
            print(f"File not found: {path}")
            continue

        df = pd.read_csv(path, engine='python', on_bad_lines='skip')

        for _, row in df.iterrows():
            did = row.get("DID")
            if not did:
                continue

            # Skip if processed in a previous run OR if we already queued it in this run
            if did in processed_dids or did in seen_dids_this_run:
                continue

            seen_dids_this_run.add(did)
            pending_accounts.append({
                "handle": row.get("Handle", ""),
                "displayName": row.get("Display Name", ""),
                "description": row.get("Bio", ""),
                "did": did
            })

    total_to_process = len(pending_accounts)
    print(f"Total new accounts to process: {total_to_process}")
    if total_to_process == 0:
        print("Everything is up to date!")
        return

    # 3. Real-time writing & Batch Processing
    # Open file in append mode ('a') so we don't overwrite existing progress
    with open(output_filename, "a", encoding="utf-8") as f:

        # Chunk the pending accounts into batches
        for i in range(0, total_to_process, batch_size):
            batch = pending_accounts[i:i + batch_size]
            print(
                f"Processing batch {i // batch_size + 1}/{(total_to_process - 1) // batch_size + 1} ({len(batch)} accounts)...")

            # Call Gemini for the batch
            batch_results = process_batch(batch)

            # Match results back to our original account data and write immediately
            for account in batch:
                did = account["did"]
                safety_info = batch_results.get(did)

                if safety_info:
                    account["safety_audit"] = {
                        "is_adult_content": safety_info.get("is_adult_content", False),
                        "explanation": safety_info.get("explanation", "Successfully audited.")
                    }
                else:
                    # Fallback if Gemini missed this specific DID in its batch response
                    account["safety_audit"] = {
                        "is_adult_content": False,
                        "explanation": "Error: Account skipped or omitted by model during batch."
                    }

                # Write to disk immediately (Real-Time)
                f.write(json.dumps(account) + "\n")

            # Flush buffer to ensure data hits the disk
            f.flush()

            # Polite pause between batches to respect rate limits
            time.sleep(2)

    print(f"\nDone! Results saved/updated in '{output_filename}'.")


if __name__ == "__main__":
    files = ["blocked_accounts_details-newenglandtopnews.csv"]
    # You can tweak the batch_size. 10-20 is usually a sweet spot for speed vs accuracy.
    process_to_jsonl(files, batch_size=10)